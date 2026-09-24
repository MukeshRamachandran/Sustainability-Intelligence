"""Public sustainability timeline: published releases + verified history.

Priority per period:
  1. OFFICIAL, publicly visible published release (Manager -> Admin -> Publish)
  2. VERIFIED historical MONTHLY values
  3. VERIFIED historical YTD values
  4. VERIFIED historical ANNUAL values
  5. static institutional reference
  6. missing
TEST releases never enter the chain.

Aggregate views (Full Year / YTD) are built here from genuine monthly values
only. Additive values are summed with their month coverage stated; ratios and
per-capita values are recomputed from summed inputs with the shared formulas
and only when every month in the window is present. Annual/YTD-only data is
never shown as a month.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.historical.calculator import current_authoritative_values, population_for
from app.models.enums import ReleaseStatus
from app.models.history import (
    HistoricalCalculationResult,
    HistoricalImportBatch,
    HistoricalPeriod,
)
from app.models.publication import PublicRelease, PublicReleaseMetadata, PublicReleasePayload
from app.models.sustainability import WasteMaterial
from app.services import sustainability_formulas as formulas
from app.services.publication import LANDFILL_DIVERSION_STATIC_REFERENCE_PCT

TIMELINE_SCHEMA_VERSION = "timeline-1.0"
DOMAINS = ("transport", "energy", "lpg", "water", "waste", "outreach")
DOMAIN_LABELS = {
    "transport": "Transport",
    "energy": "Energy",
    "lpg": "LPG",
    "water": "Water",
    "waste": "Waste",
    "outreach": "Outreach",
}
CALCULATION_DOMAIN = {
    "transport_petrol_emissions": "transport",
    "transport_diesel_emissions": "transport",
    "dg_diesel_emissions": "transport",
    "lpg_emissions": "lpg",
    "grid_total_kwh": "energy",
    "grid_electricity_emissions": "energy",
    "renewable_electricity_kwh": "energy",
    "total_electricity_consumption_kwh": "energy",
    "renewable_share_pct": "energy",
    "estimated_avoided_grid_emissions_tco2e": "energy",
    "scope1_tco2e": "ghg",
    "scope2_tco2e": "ghg",
    "operational_ghg_tco2e": "ghg",
    "operational_ghg_per_capita_kgco2e": "ghg",
    "water_consumed_kl": "water",
    "water_per_capita_l": "water",
    "total_waste_generated_kg": "waste",
    "waste_per_capita_kg": "waste",
}
# Recomputed from aggregated inputs, never summed.
RATIO_CODES = {
    "renewable_share_pct",
    "operational_ghg_per_capita_kgco2e",
    "water_per_capita_l",
    "waste_per_capita_kg",
}
NON_ADDITIVE_METRICS = {"population"}
DISPLAY_PLACES = {
    "operational_ghg_per_capita_tco2e": 9,
    "renewable_share_pct": 12,
    "estimated_avoided_grid_emissions_tco2e": 12,
    "water_per_capita_l": 12,
}


def _number(value: Decimal | None, code: str) -> int | float | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal(1).scaleb(-DISPLAY_PLACES.get(code, 6)))
    return int(rounded) if rounded == rounded.to_integral_value() else float(rounded)


@dataclass
class Value:
    code: str
    domain: str
    kind: str  # metric | calculation
    value: Decimal | None
    unit: str
    reason: str | None = None
    qualifier: str = "EXACT"
    source_kind: str = "historical_verified"
    granularity: str = "MONTHLY"
    coverage_status: str = "complete"
    months_covered: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "domain": self.domain,
            "kind": self.kind,
            "status": "available" if self.value is not None else "unavailable",
            "value": _number(self.value, self.code),
            "unit": self.unit,
            "reason": self.reason,
            "qualifier": self.qualifier,
            "source_kind": self.source_kind,
            "granularity": self.granularity,
            "coverage_status": self.coverage_status if self.value is not None else "unavailable",
            "months_covered": self.months_covered,
            "provenance": self.provenance,
        }


@dataclass
class Entry:
    key: str
    label: str
    year: int
    month: int | None
    granularity: str
    coverage_start: date
    coverage_end: date
    source_kind: str
    release_version: str | None = None
    values: dict[str, Value] = field(default_factory=dict)
    population: dict[str, Any] = field(default_factory=dict)

    def has_data(self) -> bool:
        return any(item.value is not None for item in self.values.values())


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def visible_official_releases(db: Session) -> list[tuple[PublicRelease, PublicReleasePayload]]:
    """Published releases that are official and publicly visible (no metadata row = official)."""
    rows = db.execute(
        select(PublicRelease, PublicReleasePayload, PublicReleaseMetadata)
        .join(PublicReleasePayload, PublicReleasePayload.release_id == PublicRelease.id)
        .outerjoin(PublicReleaseMetadata, PublicReleaseMetadata.release_id == PublicRelease.id)
        .where(
            PublicRelease.status.in_((ReleaseStatus.ACTIVE, ReleaseStatus.SUPERSEDED)),
            PublicRelease.published_at.is_not(None),
        )
        .order_by(PublicRelease.published_at.desc(), PublicRelease.created_at.desc())
    ).all()
    return [
        (release, payload)
        for release, payload, metadata in rows
        if metadata is None or (metadata.classification == "official" and metadata.public_visible)
    ]


def is_publicly_visible(db: Session, release_id: object) -> bool:
    metadata = db.get(PublicReleaseMetadata, release_id)
    return metadata is None or (metadata.classification == "official" and metadata.public_visible)


def _release_entry(release: PublicRelease, payload: dict[str, Any]) -> Entry | None:
    period = payload.get("period")
    if not isinstance(period, dict) or not period.get("year") or not period.get("month"):
        return None
    year, month = int(period["year"]), int(period["month"])
    entry = Entry(
        key=_month_key(year, month),
        label=f"{calendar.month_abbr[month]} {year}",
        year=year,
        month=month,
        granularity="MONTHLY",
        coverage_start=date(year, month, 1),
        coverage_end=date(year, month, calendar.monthrange(year, month)[1]),
        source_kind="published_release",
        release_version=release.version,
    )
    provenance = {"release_version": release.version, "checksum_sha256": release.checksum_sha256}

    def put(code: str, domain: str, kind: str, raw: Any, unit: str, reason: str | None = None) -> None:
        entry.values[code] = Value(
            code,
            domain,
            kind,
            None if raw is None else Decimal(str(raw)),
            unit,
            reason,
            source_kind="published_release",
            provenance=provenance,
        )

    for domain in ("transport", "energy", "lpg", "water", "waste"):
        block = payload.get(domain)
        if not isinstance(block, dict):
            continue
        for code, item in (block.get("metrics") or {}).items():
            if isinstance(item, dict) and item.get("value") is not None:
                put(code, domain, "metric", item["value"], item.get("unit") or "")
        for item in block.get("calculations") or []:
            if isinstance(item, dict) and item.get("calculation_code"):
                put(
                    item["calculation_code"],
                    domain,
                    "calculation",
                    item.get("result_value") if item.get("status") == "available" else None,
                    item.get("result_unit") or "tCO2e",
                    item.get("reason"),
                )
                if item.get("factor_value") is not None:
                    entry.values[item["calculation_code"]].provenance = {
                        **provenance,
                        "factor_code": item.get("factor_code"),
                        "factor_value": str(item.get("factor_value")),
                        "factor_set_version": item.get("factor_set_version"),
                    }
        if domain == "waste":
            for material in block.get("materials") or []:
                put(f"material:{material['code']}", "waste", "metric", material.get("quantity_kg"), "kg")
    outreach = payload.get("outreach")
    if isinstance(outreach, dict):
        for code in (
            "total_programs",
            "total_participants",
            "partner_organizations",
            "saplings_planted",
            "experts_involved",
            "volunteers_engaged",
            "volunteer_hours",
        ):
            put(code, "outreach", "metric", outreach.get(code), "")
        for theme, count in (outreach.get("themes") or {}).items():
            put(f"theme:{theme}", "outreach", "metric", count, "programmes")
        for category, count in (outreach.get("participants_by_category") or {}).items():
            put(f"audience:{category}", "outreach", "metric", count, "people")
    for code, item in (payload.get("indicators") or {}).items():
        if code in CALCULATION_DOMAIN and isinstance(item, dict):
            put(
                code,
                CALCULATION_DOMAIN[code],
                "calculation",
                item.get("value"),
                item.get("unit") or "",
                item.get("reason"),
            )
    for code in ("grid_total_kwh",):
        energy = payload.get("energy") or {}
        metric = (energy.get("metrics") or {}).get(code) if isinstance(energy, dict) else None
        if isinstance(metric, dict):
            put(code, "energy", "calculation", metric.get("value"), "kWh")
    population = payload.get("population")
    if isinstance(population, dict):
        entry.population = {key: population.get(key) for key in ("status", "value", "unit", "effective_year")}
    return entry


def _batch_provenance(db: Session) -> dict[Any, dict[str, str]]:
    return {
        batch.id: {"batch": batch.batch_name, "source_sha256": batch.source_sha256}
        for batch in db.scalars(select(HistoricalImportBatch)).all()
    }


def _historical_entry(db: Session, period: HistoricalPeriod, batches: dict[Any, dict[str, str]]) -> Entry:
    entry = Entry(
        key=_month_key(period.year, period.month) if period.month else f"{period.year}-{period.granularity}",
        label=period.display_label,
        year=period.year,
        month=period.month,
        granularity=period.granularity,
        coverage_start=period.coverage_start,
        coverage_end=period.coverage_end,
        source_kind="historical_verified",
    )
    for (domain, metric), row in current_authoritative_values(db, period.id).items():
        entry.values[metric] = Value(
            metric,
            domain,
            "metric",
            row.value_numeric,
            row.unit,
            qualifier=row.value_qualifier,
            granularity=period.granularity,
            provenance={
                **batches.get(row.source_batch_id, {}),
                "source_column": row.source_column,
                "verification_status": row.verification_status,
            },
        )
    for calc in db.scalars(
        select(HistoricalCalculationResult).where(
            HistoricalCalculationResult.period_id == period.id, HistoricalCalculationResult.is_current.is_(True)
        )
    ).all():
        provenance: dict[str, Any] = {"methodology_version": calc.methodology_version}
        if calc.factor_set_version:
            provenance.update(
                {
                    "factor_code": calc.factor_code,
                    "factor_value": str(calc.factor_value),
                    "factor_set_version": calc.factor_set_version,
                }
            )
        reported = entry.values.get(calc.calculation_code)
        if calc.result_value is None and reported is not None and reported.value is not None:
            continue  # an unavailable calculation never hides an available source-reported value
        entry.values[calc.calculation_code] = Value(
            calc.calculation_code,
            CALCULATION_DOMAIN.get(calc.calculation_code, "ghg"),
            "calculation",
            calc.result_value,
            calc.result_unit,
            calc.unavailable_reason,
            granularity=period.granularity,
            provenance=provenance,
        )
    return entry


def _derive_ratios(db: Session, entry: Entry) -> None:
    """Recompute ratios/per-capita from summed inputs; never average them."""

    def complete(code: str) -> Decimal | None:
        item = entry.values.get(code)
        return item.value if item is not None and item.coverage_status == "complete" else None

    population, population_source = population_for(db, entry.year)
    entry.population = {
        "status": "available" if population is not None else "unavailable",
        "value": _number(population, "population"),
        "unit": "people",
        "effective_year": entry.year,
        "source_kind": population_source.get("kind"),
    }
    derived = {
        "renewable_share_pct": (
            "energy",
            "%",
            formulas.renewable_share_pct(
                complete("renewable_electricity_kwh"), complete("total_electricity_consumption_kwh")
            ),
        ),
        "operational_ghg_per_capita_kgco2e": (
            "ghg",
            "kgCO2e/person",
            formulas.operational_ghg_per_capita_kgco2e(complete("operational_ghg_tco2e"), population),
        ),
        "water_per_capita_l": (
            "water",
            "L/person",
            formulas.water_per_capita_l(complete("water_consumed_kl"), population),
        ),
        "waste_per_capita_kg": (
            "waste",
            "kg/person",
            formulas.waste_per_capita_kg(complete("total_waste_generated_kg"), population),
        ),
    }
    for code, (domain, unit, derived_value) in derived.items():
        existing = entry.values.get(code)
        if existing is not None and existing.value is not None:
            continue  # a source-period calculation already exists (e.g. annual waste per person)
        reason = None if derived_value is not None else "requires_complete_coverage_and_population"
        entry.values[code] = Value(
            code,
            domain,
            "calculation",
            derived_value,
            unit,
            reason,
            source_kind=entry.source_kind,
            granularity=entry.granularity,
            provenance={"aggregation": "recomputed_from_summed_inputs"},
        )


def _source_entry(db: Session, source: Entry, key: str) -> Entry:
    entry = Entry(
        key,
        source.label,
        source.year,
        None,
        source.granularity,
        source.coverage_start,
        source.coverage_end,
        "historical_verified",
    )
    for code, value in source.values.items():
        entry.values[code] = Value(
            value.code,
            value.domain,
            value.kind,
            value.value,
            value.unit,
            value.reason,
            value.qualifier,
            "historical_verified",
            source.granularity,
            "complete",
            [],
            value.provenance,
        )
    _derive_ratios(db, entry)
    return entry


def _aggregates(db: Session, year: int, months: list[Entry], sources: list[Entry]) -> list[Entry]:
    """Aggregate views for one year, built only from genuine records.

    * Monthly-derived: Full Year when all twelve months exist, otherwise YTD
      Jan..last genuine month. Additive values are summed with coverage stated.
    * A source-reported ANNUAL/YTD record whose coverage matches that window is
      merged into it; any other source record keeps its own view (for example an
      annual waste total in a year with only some genuine months).
    """
    result: list[Entry] = []
    month_numbers = sorted(item.month for item in months if item.month)
    unmatched = list(sources)
    if month_numbers:
        last = month_numbers[-1]
        if month_numbers == list(range(1, 13)):
            granularity, key, label = "ANNUAL", f"{year}-FY", f"{year} Full Year"
        else:
            granularity, key = "YTD", f"{year}-YTD"
            label = f"{year} YTD · Jan–{calendar.month_abbr[last]}"
        start, end = date(year, 1, 1), date(year, last, calendar.monthrange(year, last)[1])
        window = [_month_key(year, month) for month in range(1, last + 1)]
        entry = Entry(key, label, year, None, granularity, start, end, "historical_aggregate")
        kinds = {item.source_kind for item in months}
        if kinds == {"published_release"}:
            entry.source_kind = "published_release_aggregate"
        elif "published_release" in kinds:
            entry.source_kind = "mixed_aggregate"
        by_code: dict[str, list[tuple[str, Value]]] = defaultdict(list)
        for month in months:
            for code, value in month.values.items():
                if value.value is not None and code not in RATIO_CODES and code not in NON_ADDITIVE_METRICS:
                    by_code[code].append((month.key, value))
        for code, items in by_code.items():
            covered = sorted(month_key for month_key, _ in items)
            sample = items[0][1]
            qualifiers = {value.qualifier for _, value in items}
            entry.values[code] = Value(
                code,
                sample.domain,
                sample.kind,
                sum((value.value for _, value in items if value.value is not None), Decimal("0")),
                sample.unit,
                qualifier="EXACT" if qualifiers == {"EXACT"} else "APPROXIMATE",
                source_kind=entry.source_kind,
                granularity=granularity,
                coverage_status="complete" if covered == window else "partial",
                months_covered=covered,
                provenance={"aggregation": "sum_of_genuine_monthly_values"},
            )
        for source in sorted(sources, key=lambda item: 0 if item.granularity == "YTD" else 1):
            if (source.coverage_start, source.coverage_end) != (start, end):
                continue
            unmatched.remove(source)
            for code, value in source.values.items():
                if code not in entry.values or entry.values[code].value is None:
                    entry.values[code] = Value(
                        value.code,
                        value.domain,
                        value.kind,
                        value.value,
                        value.unit,
                        value.reason,
                        value.qualifier,
                        "historical_verified",
                        source.granularity,
                        "complete",
                        [],
                        value.provenance,
                    )
        _derive_ratios(db, entry)
        result.append(entry)
    taken = {item.key for item in result}
    for source in sorted(unmatched, key=lambda item: (item.coverage_end, item.granularity)):
        if source.granularity == "ANNUAL" and source.coverage_start.month == 1 and source.coverage_end.month == 12:
            key = f"{year}-FY"
        else:
            key = f"{year}-YTD-{source.coverage_end.month:02d}"
        if key in taken:
            key = f"{key}-{source.coverage_start.month:02d}"
        taken.add(key)
        result.append(_source_entry(db, source, key))
    return result


STATIC_LABEL = "Institutional Reference"
# Official inventory totals: shown only with complete coverage, never as a partial sum.
OFFICIAL_GHG_TOTALS = {"scope1_tco2e", "scope2_tco2e", "operational_ghg_tco2e", "grid_electricity_emissions"}


def _aggregate_label(entry: Entry) -> str:
    if entry.granularity == "ANNUAL":
        return f"{entry.year} Annual Data"
    start, end = calendar.month_abbr[entry.coverage_start.month], calendar.month_abbr[entry.coverage_end.month]
    return f"{entry.year} YTD · {start}–{end}"


def _display_item(value: Value, entry: Entry, label: str, *, context: bool) -> dict[str, Any]:
    return {
        "value": _number(value.value, value.code),
        "unit": value.unit,
        "qualifier": value.qualifier,
        "domain": value.domain,
        "source_granularity": value.granularity if value.granularity in ("ANNUAL", "YTD") else entry.granularity,
        "source_year": entry.year,
        "source_month": entry.month,
        "source_key": entry.key,
        "display_context": context,
        "display_label": label,
    }


def _static_display(landfill: Decimal) -> dict[str, dict[str, Any]]:
    return {
        "landfill_diversion_pct": {
            "value": _number(landfill, "landfill_diversion_pct"),
            "unit": "%",
            "qualifier": "EXACT",
            "domain": "waste",
            "source_granularity": "STATIC",
            "source_year": None,
            "source_month": None,
            "source_key": None,
            "display_context": True,
            "display_label": STATIC_LABEL,
        }
    }


def _month_display(entry: Entry, aggregates: list[Entry], static: dict[str, Any]) -> dict[str, Any]:
    """What a month view SHOWS for each metric. Presentation only.

    Order: this month's own value; else a complete ANNUAL value of the year;
    else a complete YTD value whose window covers the month; else a static
    reference; else nothing (the card is hidden). A fallback is labelled with
    its true source period and flagged ``display_context``; it is never added
    to the month's ``values`` (which drive charts, exports and calculations).
    """
    display: dict[str, Any] = dict(static)
    exact_label = f"{calendar.month_name[entry.month or 1]} {entry.year}"
    for code, value in entry.values.items():
        if value.value is not None and code != "population":
            display[code] = _display_item(value, entry, exact_label, context=False)
    month_date = entry.coverage_start
    candidates = sorted(
        (item for item in aggregates if item.coverage_start <= month_date <= item.coverage_end),
        key=lambda item: 0 if item.granularity == "ANNUAL" else 1,
    )
    for aggregate in candidates:
        for code, value in aggregate.values.items():
            if code in display or code == "population" or value.value is None:
                continue
            if value.coverage_status != "complete":
                continue  # a partial-period sum is never shown as context for a month
            display[code] = _display_item(value, aggregate, _aggregate_label(aggregate), context=True)
    return display


def _aggregate_display(entry: Entry, static: dict[str, Any]) -> dict[str, Any]:
    """A Full Year / YTD view shows its own values; partial sums say how many months they cover."""
    display: dict[str, Any] = dict(static)
    label = _aggregate_label(entry)
    window = (
        (entry.coverage_end.year - entry.coverage_start.year) * 12
        + entry.coverage_end.month
        - entry.coverage_start.month
        + 1
    )
    for code, value in entry.values.items():
        if value.value is None or code == "population":
            continue
        if value.coverage_status == "partial" and code in OFFICIAL_GHG_TOTALS:
            continue  # never a partial figure under an official Scope 1 / Scope 2 / Operational GHG label
        if value.coverage_status == "partial":
            item_label = f"{entry.year} · {len(value.months_covered)} of {window} months"
        else:
            item_label = label
        display[code] = _display_item(value, entry, item_label, context=False)
    return display


def _with_hero_items(display: dict[str, Any]) -> dict[str, Any]:
    """Carbon hero figures, derived only from governed display items.

    * ``gross_emissions_tco2e`` is the public name of Operational GHG
      (Scope 1 + Scope 2; Scope 3 not included; avoided emissions never
      subtracted).
    * ``operational_ghg_per_capita_tco2e`` is the governed per-capita result
      expressed in tonnes (kgCO2e/person / 1000).
    Both inherit the source item's period, coverage rule and provenance, so a
    partial or missing Operational GHG yields no hero figure at all.
    """
    operational = display.get("operational_ghg_tco2e")
    if operational is not None:
        display["gross_emissions_tco2e"] = {**operational}
    per_capita = display.get("operational_ghg_per_capita_kgco2e")
    if per_capita is not None and per_capita["value"] is not None:
        tonnes = Decimal(str(per_capita["value"])) / 1000
        display["operational_ghg_per_capita_tco2e"] = {
            **per_capita,
            "value": _number(tonnes, "operational_ghg_per_capita_tco2e"),
            "unit": "tCO2e/person",
        }
    return display


def _domain_status(entry: Entry, aggregates: list[Entry]) -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for domain in DOMAINS:
        if any(value.value is not None and value.domain == domain for value in entry.values.values()):
            status[domain] = {"state": "available"}
            continue
        alternative = next(
            (
                aggregate
                for aggregate in aggregates
                if entry.granularity == "MONTHLY"
                and any(value.value is not None and value.domain == domain for value in aggregate.values.values())
            ),
            None,
        )
        if alternative is not None:
            kind = "annual" if alternative.granularity == "ANNUAL" else "year-to-date"
            status[domain] = {
                "state": "aggregate_only",
                "alternative_key": alternative.key,
                "message": f"Monthly {DOMAIN_LABELS[domain]} data unavailable. "
                f"{alternative.year} {kind} data is available under {alternative.label}.",
            }
        else:
            status[domain] = {
                "state": "unavailable",
                "message": f"{DOMAIN_LABELS[domain]} data is not available for {entry.label}.",
            }
    return status


def build_timeline(db: Session) -> dict[str, Any]:
    batches = _batch_provenance(db)
    monthly: dict[str, Entry] = {}
    sources_by_year: dict[int, list[Entry]] = defaultdict(list)
    for period in db.scalars(select(HistoricalPeriod).order_by(HistoricalPeriod.coverage_start)).all():
        entry = _historical_entry(db, period, batches)
        if period.granularity == "MONTHLY":
            if entry.has_data():
                monthly[entry.key] = entry
        elif period.granularity in ("ANNUAL", "YTD"):
            entry.values.pop("population", None)
            if entry.has_data():
                sources_by_year[period.year].append(entry)
    for release, payload in visible_official_releases(db):
        release_entry = _release_entry(release, payload.payload)
        if release_entry is None:
            continue
        current = monthly.get(release_entry.key)
        if current is None or current.source_kind != "published_release":
            monthly[release_entry.key] = release_entry  # priority 1 beats history

    static = _static_display(LANDFILL_DIVERSION_STATIC_REFERENCE_PCT)
    years = sorted({entry.year for entry in monthly.values()} | set(sources_by_year))
    periods: dict[str, dict[str, Any]] = {}
    selector = []
    for year in years:
        months = sorted((entry for entry in monthly.values() if entry.year == year), key=lambda item: item.month or 0)
        aggregates = [item for item in _aggregates(db, year, months, sources_by_year.get(year, [])) if item.has_data()]
        options = []
        for aggregate in aggregates:
            periods[aggregate.key] = _entry_json(aggregate, [])
            periods[aggregate.key]["display"] = _with_hero_items(_aggregate_display(aggregate, static))
            label = "Full Year" if aggregate.key == f"{year}-FY" else aggregate.label.split(" ", 1)[1]
            options.append({"key": aggregate.key, "label": label, "granularity": aggregate.granularity})
        population, source = population_for(db, year)
        for entry in months:
            if not entry.population:
                entry.population = {
                    "status": "available" if population is not None else "unavailable",
                    "value": _number(population, "population"),
                    "unit": "people",
                    "effective_year": year,
                    "source_kind": source.get("kind"),
                }
            periods[entry.key] = _entry_json(entry, aggregates)
            periods[entry.key]["display"] = _with_hero_items(_month_display(entry, aggregates, static))
            options.append({"key": entry.key, "label": calendar.month_abbr[entry.month or 1], "granularity": "MONTHLY"})
        selector.append({"year": year, "options": options})
    latest = max(monthly.values(), key=lambda item: (item.year, item.month or 0), default=None)
    materials = {row.code: row.display_name for row in db.scalars(select(WasteMaterial)).all()}
    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "default_key": latest.key if latest else None,
        "selector": selector,
        "periods": periods,
        "labels": {f"material:{code}": name for code, name in sorted(materials.items())},
        # Static institutional references are not period data; one backend constant is the authority.
        "static_references": {
            "landfill_diversion_pct": {
                "value": _number(LANDFILL_DIVERSION_STATIC_REFERENCE_PCT, "landfill_diversion_pct"),
                "unit": "%",
                "kind": "static_institutional_reference",
                "source_reference": "Legacy institutional dashboard reference; not derived from monthly waste",
            }
        },
    }


def _entry_json(entry: Entry, aggregates: list[Entry]) -> dict[str, Any]:
    return {
        "key": entry.key,
        "label": entry.label,
        "year": entry.year,
        "month": entry.month,
        "granularity": entry.granularity,
        "coverage_start": entry.coverage_start.isoformat(),
        "coverage_end": entry.coverage_end.isoformat(),
        "coverage_status": "complete"
        if all(value.coverage_status == "complete" for value in entry.values.values() if value.value is not None)
        else "partial",
        "source_kind": entry.source_kind,
        "release_version": entry.release_version,
        "population": entry.population,
        "domains": _domain_status(entry, aggregates),
        "values": {code: value.as_json() for code, value in sorted(entry.values.items())},
    }


__all__ = ["build_timeline", "is_publicly_visible", "visible_official_releases"]
