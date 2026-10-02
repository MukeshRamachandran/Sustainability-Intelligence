"""Parse institutional CSV sources into typed historical observations.

The legacy CSVs are irregular (side-by-side blocks, year header rows, wide
year columns, qualified numbers such as ``20+``). Each parser here is driven
by a JSON mapping in ``mappings/`` and emits:

* ``Observation`` - one source-reported value with its true granularity,
  period coverage, raw source row and column;
* ``InternalCheck`` - a consistency check the source itself allows (for
  example a printed total versus the sum of its rows).

Nothing is ever interpolated, allocated across months or defaulted to zero:
a blank cell produces no observation at all.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

WATER_BLOCK = re.compile(r"water consumption (\d{4})", re.IGNORECASE)
MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})


@dataclass(frozen=True)
class PeriodKey:
    granularity: str
    year: int
    month: int | None
    coverage_start: date
    coverage_end: date

    @staticmethod
    def monthly(year: int, month: int) -> PeriodKey:
        last = calendar.monthrange(year, month)[1]
        return PeriodKey("MONTHLY", year, month, date(year, month, 1), date(year, month, last))

    @staticmethod
    def spanning(granularity: str, start: date, end: date) -> PeriodKey:
        return PeriodKey(granularity, start.year, None, start, end)

    @property
    def label(self) -> str:
        if self.granularity == "MONTHLY" and self.month is not None:
            return f"{calendar.month_abbr[self.month]} {self.year}"
        span = f"{calendar.month_abbr[self.coverage_start.month]}–{calendar.month_abbr[self.coverage_end.month]}"
        if self.granularity == "ANNUAL":
            return f"{self.year} Full Year"
        if self.granularity == "YTD":
            return f"{self.year} YTD · {span}"
        return f"{self.year} Static reference"

    def months(self) -> list[tuple[int, int]]:
        result = []
        year, month = self.coverage_start.year, self.coverage_start.month
        while (year, month) <= (self.coverage_end.year, self.coverage_end.month):
            result.append((year, month))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return result


@dataclass
class Observation:
    period: PeriodKey
    domain: str
    metric_code: str
    value: Decimal
    unit: str
    qualifier: str
    row_number: int
    source_column: str
    verification_hint: str = "VERIFIED"
    notes: list[str] = field(default_factory=list)
    # Monthly metrics whose summed value this aggregate must equal (default: itself).
    reconcile_against: tuple[str, ...] | None = None
    # Stored with provenance but never AUTHORITATIVE: never public, never a
    # calculation input (for example a source-reported cylinder count).
    reference_only: bool = False
    # A source-reported result the backend must independently reproduce; a
    # disagreement is recorded as a reconciliation conflict.
    compare_to_calculation: str | None = None


@dataclass
class InternalCheck:
    description: str
    expected: Decimal
    actual: Decimal
    affects: list[tuple[PeriodKey, str, str]]  # (period, domain, metric_code)
    # An advisory check never blocks: a failure is kept as a quality note on the
    # affected values instead of marking them CONFLICT.
    advisory: bool = False

    @property
    def passed(self) -> bool:
        return self.expected == self.actual


@dataclass
class ParsedSource:
    rows: list[list[str]]
    observations: list[Observation] = field(default_factory=list)
    checks: list[InternalCheck] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_rows(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig")
    return [list(row) for row in csv.reader(io.StringIO(text))]


def parse_number(raw: str) -> tuple[Decimal, str] | None:
    """Return (value, qualifier) or None for a blank cell. ``1,828+`` -> (1828, AT_LEAST)."""
    text = raw.strip().replace(",", "")
    if not text or text in {"-", "null", "NULL"}:
        return None
    qualifier = "EXACT"
    if text.endswith("+"):
        qualifier, text = "AT_LEAST", text[:-1].strip()
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {raw!r}") from exc
    if not value.is_finite():
        raise ValueError(f"not a finite number: {raw!r}")
    return value, qualifier


def parse_month(raw: str) -> int | None:
    return MONTHS.get(raw.strip().lower())


def _cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _span_period(rule: dict[str, Any]) -> PeriodKey:
    return PeriodKey.spanning(rule["granularity"], _date(rule["coverage_start"]), _date(rule["coverage_end"]))


def _observe(
    parsed: ParsedSource,
    mapping: dict[str, Any],
    period: PeriodKey,
    metric: dict[str, Any],
    raw: str,
    row_number: int,
    column: str,
    *,
    hint: str = "VERIFIED",
    notes: list[str] | None = None,
) -> Observation | None:
    try:
        number = parse_number(raw)
    except ValueError as exc:
        parsed.invalid.append(f"row {row_number} column {column!r}: {exc}")
        return None
    if number is None:
        return None
    value, qualifier = number
    value = value * Decimal(str(metric.get("multiply", 1)))
    if metric.get("qualifier"):
        qualifier = metric["qualifier"]
    item_notes = list(notes or [])
    if metric.get("note"):
        item_notes.append(metric["note"])
    observation = Observation(
        period=period,
        domain=metric.get("domain", mapping["domain"]),
        metric_code=metric["metric_code"],
        value=value,
        unit=metric["unit"],
        qualifier=qualifier,
        row_number=row_number,
        source_column=column,
        verification_hint=metric.get("verification", hint),
        notes=item_notes,
        reconcile_against=tuple(metric["reconcile_against"]) if metric.get("reconcile_against") else None,
        reference_only=bool(metric.get("reference_only", False)),
        compare_to_calculation=metric.get("compare_to_calculation"),
    )
    parsed.observations.append(observation)
    return observation


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------


def parse_wide_monthly(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """Header row, then one row per month: Year, Month, metric columns...

    A source without a year column states its year once in the mapping
    (``fixed_year``). ``row_checks`` are per-row equations the source allows.
    """
    options = mapping["options"]
    header_index = options["header_row"]
    header = [cell.strip() for cell in parsed.rows[header_index]]
    columns = {name.strip(): metric for name, metric in mapping["columns"].items()}
    year_column = options.get("year_column")
    for name in header:
        if name and name not in columns and name not in (year_column, options["month_column"]):
            parsed.ignored.append(f"column {name!r} (not mapped; kept in the raw source row)")
    for row_number, row in enumerate(parsed.rows[header_index + 1 :], start=header_index + 2):
        if not any(cell.strip() for cell in row):
            continue
        year_raw = (
            _cell(row, header.index(year_column)).strip() if year_column else str(options.get("fixed_year", ""))
        )
        month = parse_month(_cell(row, header.index(options["month_column"])))
        if not year_raw.isdigit() or month is None:
            parsed.invalid.append(f"row {row_number}: unrecognised year/month {row[:2]!r}")
            continue
        period = PeriodKey.monthly(int(year_raw), month)
        observed = []
        for index, name in enumerate(header):
            if name in columns:
                item = _observe(parsed, mapping, period, columns[name], _cell(row, index), row_number, name)
                if item is not None:
                    observed.append(item)
        cells = {name: _cell(row, index) for index, name in enumerate(header) if name}
        for check in options.get("row_checks", []):
            _row_check(parsed, check, cells, period, observed)


def _row_check(
    parsed: ParsedSource,
    check: dict[str, Any],
    cells: dict[str, str],
    period: PeriodKey,
    observed: list[Observation],
) -> None:
    """expected = product(product) or sum(plus) - sum(minus); skipped if a cell is blank."""
    expected = parse_number(cells.get(check["expected"], ""))
    if "product" in check:
        parts = [parse_number(cells.get(name, "")) for name in check["product"]]
    else:
        parts = [parse_number(cells.get(name, "")) for name in check["plus"] + check.get("minus", [])]
    if expected is None or any(part is None for part in parts):
        return
    values = [part[0] for part in parts if part is not None]
    if "product" in check:
        actual = Decimal("1")
        for value in values:
            actual *= value
    else:
        plus = len(check["plus"])
        actual = sum(values[:plus], Decimal("0")) - sum(values[plus:], Decimal("0"))
    parsed.checks.append(
        InternalCheck(
            description=f"{period.label}: {check['description']}",
            expected=expected[0],
            actual=actual,
            affects=[(item.period, item.domain, item.metric_code) for item in observed if not item.reference_only]
            or [(item.period, item.domain, item.metric_code) for item in observed],
            advisory=bool(check.get("advisory", False)),
        )
    )


def parse_year_block_monthly(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """Month rows grouped under a bare year row (``2025,,,``)."""
    options = mapping["options"]
    header = [cell.strip() for cell in parsed.rows[options["header_row"]]]
    columns = {int(index): metric for index, metric in mapping["columns_by_index"].items()}
    for index, name in enumerate(header):
        if index and index not in columns and name:
            parsed.ignored.append(f"column {index} {name!r} (not mapped)")
    year: int | None = None
    for row_number, row in enumerate(parsed.rows[options["header_row"] + 1 :], start=options["header_row"] + 2):
        first = _cell(row, 0).strip()
        if first.isdigit() and not any(cell.strip() for cell in row[1:]):
            year = int(first)
            continue
        month = parse_month(first)
        if month is None or year is None:
            if any(cell.strip() for cell in row):
                parsed.invalid.append(f"row {row_number}: unrecognised row {row[:3]!r}")
            continue
        period = PeriodKey.monthly(year, month)
        for index, metric in columns.items():
            _observe(parsed, mapping, period, metric, _cell(row, index), row_number, header[index] or f"col{index}")
        for check in options.get("row_sum_checks", []):
            parts = [parse_number(_cell(row, index)) for index in check["parts"]]
            total = parse_number(_cell(row, check["total"]))
            if total is None or any(part is None for part in parts):
                continue
            parsed.checks.append(
                InternalCheck(
                    description=f"{period.label}: {check['description']}",
                    expected=total[0],
                    actual=sum((part[0] for part in parts if part is not None), Decimal("0")),
                    affects=[(period, mapping["domain"], columns[index]["metric_code"]) for index in check["parts"]],
                )
            )


def parse_long_monthly(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """year, month, [category], value - one observation per row."""
    options = mapping["options"]
    header = [cell.strip() for cell in parsed.rows[0]]
    year_index = header.index(options["year_column"])
    month_index = header.index(options["month_column"])
    value_index = header.index(options["value_column"])
    category_index = header.index(options["category_column"]) if options.get("category_column") else None
    for row_number, row in enumerate(parsed.rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        year_raw = _cell(row, year_index).strip()
        month = parse_month(_cell(row, month_index))
        if not year_raw.isdigit() or month is None:
            parsed.invalid.append(f"row {row_number}: unrecognised year/month {row[:3]!r}")
            continue
        category = _cell(row, category_index).strip() if category_index is not None else "_"
        metric = mapping["categories"].get(category)
        if metric is None:
            parsed.ignored.append(f"row {row_number}: category {category!r} not mapped")
            continue
        column = f"{header[value_index]} [{category}]" if category_index is not None else header[value_index]
        _observe(
            parsed,
            mapping,
            PeriodKey.monthly(int(year_raw), month),
            metric,
            _cell(row, value_index),
            row_number,
            column,
        )


def parse_paired_monthly(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """Side-by-side blocks, each (year, month, value) under a block title."""
    options = mapping["options"]
    for block in mapping["blocks"]:
        start = block["first_column"]
        for row_number, row in enumerate(parsed.rows[options["first_data_row"] :], start=options["first_data_row"] + 1):
            year_raw = _cell(row, start).strip()
            month = parse_month(_cell(row, start + 1))
            if not year_raw.isdigit() or month is None:
                if any(cell.strip() for cell in row[start : start + 3]):
                    parsed.invalid.append(f"row {row_number}: unrecognised {block['title']} row")
                continue
            _observe(
                parsed,
                mapping,
                PeriodKey.monthly(int(year_raw), month),
                block["metric"],
                _cell(row, start + 2),
                row_number,
                f"{block['title']} consumption_litre",
            )


def parse_period_totals(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """One reported aggregate per row, with explicit start/end months."""
    header = [cell.strip() for cell in parsed.rows[0]]
    col = {name: header.index(name) for name in header if name}
    metric = mapping["metric"]
    for row_number, row in enumerate(parsed.rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        year = int(_cell(row, col["year"]))
        first, last = (
            parse_month(_cell(row, col["period_start_month"])),
            parse_month(_cell(row, col["period_end_month"])),
        )
        if first is None or last is None:
            parsed.invalid.append(f"row {row_number}: missing coverage months")
            continue
        granularity = "ANNUAL" if (first, last) == (1, 12) else "YTD"
        period = PeriodKey.spanning(
            granularity, date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1])
        )
        note = _cell(row, col["notes"]).strip() if "notes" in col else ""
        _observe(
            parsed,
            mapping,
            period,
            metric,
            _cell(row, col[mapping["value_column"]]),
            row_number,
            mapping["value_column"],
            notes=[f"source note: {note}"] if note else None,
        )


def parse_year_columns(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """Labelled rows with one value column per year (waste inventory, outreach).

    ``year_rules`` gives each year column its true granularity and coverage.
    A column whose coverage end is not stated in the source is imported
    UNVERIFIED so it cannot be published until the owner confirms coverage.
    """
    year_columns: dict[int, int] = {}
    section: str | None = None
    for row_number, row in enumerate(parsed.rows, start=1):
        label = _cell(row, 0).strip()
        rest = [cell.strip() for cell in row[1:]]
        if label in mapping["sections"]:
            section = mapping["sections"][label]
            continue
        if not label and any(cell.isdigit() and len(cell) == 4 for cell in rest):
            year_columns = {int(cell): index + 1 for index, cell in enumerate(rest) if cell.isdigit()}
            continue
        if label.lower() == "year" and any(cell.isdigit() for cell in rest):
            year_columns = {int(cell): index + 1 for index, cell in enumerate(rest) if cell.isdigit()}
            continue
        if not label or section is None:
            continue
        rows = mapping["rows"].get(section, {})
        metric = rows.get(label) or rows.get(label.strip())
        if metric is None:
            if label not in mapping.get("header_labels", []):
                parsed.ignored.append(f"row {row_number} [{section}] {label!r} not mapped")
            continue
        for year, index in year_columns.items():
            rule = mapping["year_rules"].get(str(year))
            if rule is None:
                continue
            hint = "VERIFIED" if rule.get("coverage_confirmed", True) else "UNVERIFIED"
            notes = [rule["note"]] if rule.get("note") else []
            _observe(
                parsed,
                mapping,
                _span_period(rule),
                metric,
                _cell(row, index),
                row_number,
                f"{label} [{year}]",
                hint=hint,
                notes=notes,
            )
    for check in mapping.get("sum_checks", []):
        by_key: dict[tuple[PeriodKey, str], Observation] = {
            (item.period, item.metric_code): item for item in parsed.observations
        }
        periods = {item.period for item in parsed.observations}
        for period in periods:
            parts = [
                item
                for item in parsed.observations
                if item.period == period and item.metric_code.startswith(check["parts_prefix"])
            ]
            total = by_key.get((period, check["total"]))
            if not parts or total is None:
                continue
            parsed.checks.append(
                InternalCheck(
                    description=f"{period.label}: {check['description']}",
                    expected=total.value,
                    actual=sum((item.value for item in parts), Decimal("0")),
                    affects=[(period, total.domain, total.metric_code)],
                )
            )
    for check in mapping.get("equation_checks", []):
        for period in {item.period for item in parsed.observations}:
            values = {item.metric_code: item for item in parsed.observations if item.period == period}
            if check["total"] not in values or any(part not in values for part in check["parts"]):
                continue
            parsed.checks.append(
                InternalCheck(
                    description=f"{period.label}: {check['description']}",
                    expected=values[check["total"]].value,
                    actual=sum((values[part].value for part in check["parts"]), Decimal("0")),
                    affects=[(period, values[check["total"]].domain, check["total"])],
                )
            )


def parse_water_blocks(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    """The institutional water workbook: a 2025 block and a 2026 block.

    2025: one monthly consumption column, a printed column total, an annual
    recycled figure and an annual TWAD / Borewell / Total line.
    2026: an annual-to-date recycled figure and monthly TWAD / Borewell /
    Procured / Total columns.
    """
    rules = mapping["year_rules"]
    year: int | None = None
    monthly_header: list[str] | None = None
    annual_header: list[str] | None = None
    for row_number, row in enumerate(parsed.rows, start=1):
        cells = [cell.strip() for cell in row]
        first = cells[0] if cells else ""
        lower = first.lower()
        block = WATER_BLOCK.fullmatch(first)
        if block:
            year = int(block.group(1))
            monthly_header = annual_header = None
            continue
        if year is None:
            continue
        rule = rules[str(year)]
        if lower.startswith("total water recy"):
            agg = rule["recycled_period"]
            hint = "VERIFIED" if agg.get("coverage_confirmed", True) else "UNVERIFIED"
            _observe(
                parsed,
                mapping,
                _span_period(agg),
                mapping["metrics"]["recycled"],
                cells[1],
                row_number,
                first,
                hint=hint,
                notes=[agg["note"]] if agg.get("note") else None,
            )
            continue
        if lower == "month":
            monthly_header = cells
            continue
        if lower.startswith("twad consumption"):
            annual_header = cells
            continue
        if annual_header is not None and first and first[0].isdigit():
            period = _span_period(rule["annual_period"])
            for index, name in enumerate(annual_header):
                metric = mapping["annual_columns"].get(name)
                if metric:
                    _observe(parsed, mapping, period, metric, _cell(row, index), row_number, name)
            annual_header = None
            continue
        if lower == "total" and monthly_header is not None:
            expected = parse_number(cells[1])
            monthly = [
                item
                for item in parsed.observations
                if item.period.granularity == "MONTHLY"
                and item.period.year == year
                and item.metric_code == "water_consumed_kl"
            ]
            if expected is not None and monthly:
                parsed.checks.append(
                    InternalCheck(
                        description=f"{year}: printed monthly column total equals the sum of its months",
                        expected=expected[0],
                        actual=sum((item.value for item in monthly), Decimal("0")),
                        affects=[(item.period, "water", "water_consumed_kl") for item in monthly],
                    )
                )
            continue
        month = parse_month(first)
        if month is not None and monthly_header is not None:
            period = PeriodKey.monthly(year, month)
            observed: dict[str, Decimal] = {}
            total_column: tuple[str, Decimal] | None = None
            for index, name in enumerate(monthly_header[1:], start=1):
                if not name:
                    continue
                if name in mapping["monthly_total_check_columns"]:
                    number = parse_number(_cell(row, index))
                    if number is not None:
                        total_column = (name, number[0])
                    continue
                metric = mapping["monthly_columns"].get(name)
                if metric is None:
                    parsed.ignored.append(f"row {row_number}: column {name!r} not mapped")
                    continue
                item = _observe(parsed, mapping, period, metric, _cell(row, index), row_number, name)
                if item is not None:
                    observed[item.metric_code] = item.value
            if total_column is not None and observed:
                parsed.checks.append(
                    InternalCheck(
                        description=f"{period.label}: printed '{total_column[0]}' equals TWAD + Borewell + Private",
                        expected=total_column[1],
                        actual=sum(observed.values(), Decimal("0")),
                        affects=[(period, "water", code) for code in observed],
                    )
                )


def parse_annual_rows(parsed: ParsedSource, mapping: dict[str, Any]) -> None:
    header = [cell.strip() for cell in parsed.rows[0]]
    for row_number, row in enumerate(parsed.rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        year = int(_cell(row, header.index("year")))
        period = PeriodKey.spanning("ANNUAL", date(year, 1, 1), date(year, 12, 31))
        for name, metric in mapping["columns"].items():
            _observe(parsed, mapping, period, metric, _cell(row, header.index(name)), row_number, name)


PARSERS: dict[str, Callable[[ParsedSource, dict[str, Any]], None]] = {
    "wide_monthly": parse_wide_monthly,
    "year_block_monthly": parse_year_block_monthly,
    "long_monthly": parse_long_monthly,
    "paired_monthly": parse_paired_monthly,
    "period_totals": parse_period_totals,
    "year_columns": parse_year_columns,
    "water_blocks": parse_water_blocks,
    "annual_rows": parse_annual_rows,
}


def parse_source(content: bytes, mapping: dict[str, Any]) -> ParsedSource:
    parsed = ParsedSource(rows=read_rows(content))
    PARSERS[mapping["parser"]](parsed, mapping)
    return parsed
