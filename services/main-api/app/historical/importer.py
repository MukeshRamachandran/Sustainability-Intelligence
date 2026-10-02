"""Historical import CLI.

    python -m app.historical.importer --source-root <repo root> --dry-run [--report FILE]
    python -m app.historical.importer --source-root <repo root> --commit

``--dry-run`` only reads (SELECT) from the database. It parses and reconciles
every mapped source and computes the would-be calculations in memory.

``--commit`` writes in one transaction: import batches, raw source rows,
periods, reconciled metric values, conflicts, then historical calculations.
Running it again with unchanged sources is a no-op (batches are identified by
source SHA-256 + mapping code + mapping version). A changed file under an
existing mapping version is refused: bump the mapping version and follow the
correction procedure in HISTORICAL_DATA_ARCHITECTURE.md.

A mapping version that only *reinterprets* the same source bytes (for example
a unit correction) declares ``reinterprets`` and needs an owner-approved
``unit_corrections`` entry in resolutions.json. Each corrected value is a new
version whose ``supersedes_id`` points at the value it replaces; the numeric
value must be unchanged, and the old interpretation stays traceable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.historical.calculator import PeriodCalculator, calculate_all
from app.historical.sources import PeriodKey, parse_source, sha256_bytes
from app.historical.validator import (
    LoadedSource,
    PlannedValue,
    ReconciliationPlan,
    precision_only_difference,
    reconcile,
)
from app.models.history import (
    HistoricalCalculationResult,
    HistoricalConflict,
    HistoricalImportBatch,
    HistoricalMetricValue,
    HistoricalPeriod,
    HistoricalSourceRow,
)

MAPPING_DIR = Path(__file__).resolve().parent / "mappings"


class ImportRefused(RuntimeError):
    pass


def load_mappings(directory: Path = MAPPING_DIR, only: set[str] | None = None) -> list[dict[str, Any]]:
    mappings = []
    for path in sorted(directory.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        if "code" not in body or (only and body["code"] not in only):
            continue
        reference = PurePosixPath(body["source_reference"])
        if reference.is_absolute() or ".." in reference.parts:
            raise ImportRefused(f"{path.name}: source_reference must be repository-relative")
        mappings.append(body)
    return mappings


def load_resolutions(directory: Path = MAPPING_DIR) -> list[dict[str, Any]]:
    path = directory / "resolutions.json"
    return list(json.loads(path.read_text(encoding="utf-8")).get("resolutions", [])) if path.exists() else []


def load_coverage_confirmations(directory: Path = MAPPING_DIR) -> list[dict[str, Any]]:
    path = directory / "resolutions.json"
    return (
        list(json.loads(path.read_text(encoding="utf-8")).get("coverage_confirmations", []))
        if path.exists()
        else []
    )


def load_unit_corrections(directory: Path = MAPPING_DIR) -> list[dict[str, Any]]:
    path = directory / "resolutions.json"
    return list(json.loads(path.read_text(encoding="utf-8")).get("unit_corrections", [])) if path.exists() else []


UNIT_CORRECTION_FIELDS = (
    "id",
    "mapping_code",
    "from_mapping_version",
    "to_mapping_version",
    "domain",
    "from_metric_code",
    "from_unit",
    "to_metric_code",
    "to_unit",
    "reason",
    "approved_by",
    "approved_at",
)


def load_sources(source_root: Path, mappings: list[dict[str, Any]]) -> list[LoadedSource]:
    sources = []
    for mapping in mappings:
        path = source_root / mapping["source_reference"]
        content = path.read_bytes()
        sources.append(LoadedSource(mapping, parse_source(content, mapping), sha256_bytes(content), path.name))
    return sources


@dataclass
class ImportSummary:
    sources: list[dict[str, Any]] = field(default_factory=list)
    new_batches: int = 0
    existing_batches: int = 0
    inserted_values: int = 0
    versioned_values: int = 0
    unchanged_values: int = 0
    inserted_conflicts: int = 0
    updated_conflicts: int = 0
    inserted_calculations: int = 0
    unchanged_calculations: int = 0
    calculations_preview: dict[str, dict[str, str]] = field(default_factory=dict)
    reinterpreted: list[dict[str, str]] = field(default_factory=list)
    comparisons: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Reinterpretation:
    entry: dict[str, Any]
    prior_batch: HistoricalImportBatch | None


def _reinterpretation(
    db: Session, source: LoadedSource, corrections: list[dict[str, Any]]
) -> Reinterpretation | None:
    reference = source.mapping.get("reinterprets")
    if not reference:
        return None
    entry = next((item for item in corrections if item.get("id") == reference.get("unit_correction")), None)
    if entry is None:
        raise ImportRefused(
            f"{source.code}: reinterpretation {reference!r} has no owner-approved unit_corrections entry"
        )
    missing = [name for name in UNIT_CORRECTION_FIELDS if entry.get(name) in (None, "")]
    if missing:
        raise ImportRefused(f"{source.code}: unit correction {entry.get('id')!r} is missing {missing}")
    if entry["mapping_code"] != source.code or entry["to_mapping_version"] != source.mapping["version"]:
        raise ImportRefused(f"{source.code}: unit correction {entry['id']!r} does not cover this mapping version")
    if entry.get("numeric_values_unchanged") is not True:
        raise ImportRefused(f"{source.code}: a unit correction must keep numeric source values unchanged")
    prior = db.scalar(
        select(HistoricalImportBatch).where(
            HistoricalImportBatch.mapping_code == entry["mapping_code"],
            HistoricalImportBatch.mapping_version == entry["from_mapping_version"],
        )
    )
    if prior is not None and prior.source_sha256 != source.sha256:
        raise ImportRefused(
            f"{source.code}: unit correction {entry['id']!r} reinterprets the bytes imported as "
            f"{prior.batch_name} (sha256 {prior.source_sha256[:12]}...), but the file changed. "
            "Restore the original source; a reinterpretation must never pretend the source changed."
        )
    return Reinterpretation(entry, prior)


def _existing_batches(db: Session, sources: list[LoadedSource]) -> dict[str, HistoricalImportBatch]:
    existing: dict[str, HistoricalImportBatch] = {}
    for source in sources:
        rows = db.scalars(select(HistoricalImportBatch).where(HistoricalImportBatch.mapping_code == source.code)).all()
        for row in rows:
            if row.source_sha256 == source.sha256 and row.mapping_version == source.mapping["version"]:
                existing[source.code] = row
            elif row.mapping_version == source.mapping["version"]:
                raise ImportRefused(
                    f"{source.code} v{row.mapping_version} was already imported from a different file "
                    f"(sha256 {row.source_sha256[:12]}...); the source changed. Bump the mapping version and "
                    "record the correction instead of overwriting history."
                )
    return existing


def _batch_status(values: list[PlannedValue]) -> str:
    statuses = {value.verification_status for value in values}
    if statuses == {"REJECTED"}:
        return "REJECTED"
    if statuses == {"VERIFIED"}:
        return "VERIFIED"
    return "RECONCILED"


def _period_row(
    db: Session, cache: dict[PeriodKey, HistoricalPeriod], key: PeriodKey, *, create: bool
) -> HistoricalPeriod:
    if key in cache:
        return cache[key]
    row = db.scalar(
        select(HistoricalPeriod).where(
            HistoricalPeriod.granularity == key.granularity,
            HistoricalPeriod.coverage_start == key.coverage_start,
            HistoricalPeriod.coverage_end == key.coverage_end,
        )
    )
    if row is None:
        row = HistoricalPeriod(
            id=uuid4(),
            year=key.year,
            month=key.month,
            granularity=key.granularity,
            coverage_start=key.coverage_start,
            coverage_end=key.coverage_end,
            display_label=key.label,
        )
        if create:
            db.add(row)
            db.flush()
    cache[key] = row
    return row


def _current_value(
    db: Session, period_id: UUID, domain: str, metric: str, batch_id: UUID
) -> HistoricalMetricValue | None:
    rows = db.scalars(
        select(HistoricalMetricValue)
        .where(
            HistoricalMetricValue.period_id == period_id,
            HistoricalMetricValue.domain == domain,
            HistoricalMetricValue.metric_code == metric,
            HistoricalMetricValue.source_batch_id == batch_id,
        )
        .order_by(HistoricalMetricValue.version.desc())
    ).all()
    return rows[0] if rows else None


def _notes(value: PlannedValue) -> str | None:
    return "; ".join(dict.fromkeys(value.notes)) or None


def _supersede_prior_interpretation(
    db: Session,
    link: Reinterpretation,
    candidate: HistoricalMetricValue,
    batch: HistoricalImportBatch,
    period: HistoricalPeriod,
    summary: ImportSummary,
    *,
    commit: bool,
) -> None:
    """Link a corrected value to the interpretation it replaces (append-only)."""
    entry = link.entry
    prior_batch = link.prior_batch
    if prior_batch is None or (candidate.domain, candidate.metric_code) != (entry["domain"], entry["to_metric_code"]):
        return
    prior = _current_value(db, period.id, entry["domain"], entry["from_metric_code"], prior_batch.id)
    if prior is None:
        return
    if db.scalar(select(HistoricalMetricValue.id).where(HistoricalMetricValue.supersedes_id == prior.id)):
        raise ImportRefused(f"{period.display_label} {prior.metric_code} v{prior.version} is already superseded")
    if prior.unit != entry["from_unit"] or prior.value_numeric != candidate.value_numeric:
        raise ImportRefused(
            f"{period.display_label}: unit correction {entry['id']!r} expected {entry['from_unit']} "
            f"{candidate.value_numeric}, found {prior.unit} {prior.value_numeric}; numbers must not change"
        )
    candidate.version = prior.version + 1
    candidate.supersedes_id = prior.id
    candidate.notes = "; ".join(
        filter(
            None,
            (
                candidate.notes,
                f"unit correction {entry['id']}: supersedes {prior.metric_code} ({prior.unit}) "
                f"v{prior.version} from {prior_batch.batch_name}; numeric source value unchanged",
            ),
        )
    )
    summary.reinterpreted.append(
        {
            "period": period.display_label,
            "from": f"{prior.metric_code} {prior.value_numeric.normalize():f} {prior.unit}",
            "to": f"{candidate.metric_code} {candidate.value_numeric.normalize():f} {candidate.unit}",
        }
    )
    key = "|".join(
        (
            "unit_reinterpretation",
            f"{period.granularity}|{period.coverage_start}|{period.coverage_end}",
            entry["domain"],
            entry["to_metric_code"],
            prior_batch.batch_name,
            batch.batch_name,
        )
    )
    if not commit or db.scalar(select(HistoricalConflict.id).where(HistoricalConflict.conflict_key == key)):
        return
    summary.inserted_conflicts += 1
    db.add(
        HistoricalConflict(
            id=uuid4(),
            conflict_key=key,
            conflict_type="unit_reinterpretation",
            domain=entry["domain"],
            metric_code=entry["to_metric_code"],
            period_id=period.id,
            source_a_batch_id=prior_batch.id,
            value_a=prior.value_numeric,
            source_b_batch_id=batch.id,
            value_b=candidate.value_numeric,
            detail=(
                f"{prior_batch.batch_name} normalized {prior.value_numeric.normalize():f} as "
                f"{prior.metric_code} ({prior.unit}); {batch.batch_name} normalizes the same source value "
                f"as {candidate.metric_code} ({candidate.unit}). Numeric value unchanged."
            ),
            resolution_status="RESOLVED",
            chosen_batch_id=batch.id,
            resolution_reason=f"{entry['reason']} (approved by {entry['approved_by']} on {entry['approved_at']})",
            resolved_at=datetime.now(UTC),
        )
    )


def _record_coverage_confirmation(
    db: Session,
    value: PlannedValue,
    previous: HistoricalMetricValue,
    candidate: HistoricalMetricValue,
    batch: HistoricalImportBatch,
    period: HistoricalPeriod,
    summary: ImportSummary,
) -> None:
    """Audit record for an owner-confirmed coverage (C1), like a unit correction."""
    entry = value.confirmation or {}
    key = "|".join(
        (
            "coverage_confirmation",
            f"{period.granularity}|{period.coverage_start}|{period.coverage_end}",
            candidate.domain,
            candidate.metric_code,
            batch.batch_name,
        )
    )
    if db.scalar(select(HistoricalConflict.id).where(HistoricalConflict.conflict_key == key)):
        return
    summary.inserted_conflicts += 1
    end = "confirmed by the owner" if candidate.coverage_end_stated else "not stated by the source"
    db.add(
        HistoricalConflict(
            id=uuid4(),
            conflict_key=key,
            conflict_type="coverage_confirmation",
            domain=candidate.domain,
            metric_code=candidate.metric_code,
            period_id=period.id,
            source_a_batch_id=batch.id,
            value_a=previous.value_numeric,
            source_b_batch_id=batch.id,
            value_b=candidate.value_numeric,
            detail=(
                f"{batch.batch_name} reported {candidate.metric_code} = {candidate.value_numeric.normalize():f} "
                f"without a confirmed coverage (v{previous.version} {previous.verification_status}); "
                f"owner-confirmed as a {period.year} year-to-date value (coverage end month {end})."
            ),
            resolution_status="RESOLVED",
            chosen_batch_id=batch.id,
            resolution_reason=(
                f"{entry.get('reason')} (approved by {entry.get('approved_by')} on {entry.get('approved_at')})"
            ),
            resolved_at=datetime.now(UTC),
        )
    )


def run(
    db: Session,
    sources: list[LoadedSource],
    plan: ReconciliationPlan,
    *,
    commit: bool,
    unit_corrections: list[dict[str, Any]] | None = None,
) -> ImportSummary:
    summary = ImportSummary()
    existing = _existing_batches(db, sources)
    corrections = load_unit_corrections() if unit_corrections is None else unit_corrections
    reinterpretations: dict[str, Reinterpretation] = {}
    for source in sources:
        link = _reinterpretation(db, source, corrections)
        if link is not None:
            reinterpretations[source.code] = link
    batches: dict[str, HistoricalImportBatch] = {}
    values_by_source: dict[str, list[PlannedValue]] = defaultdict(list)
    for value in plan.values:
        values_by_source[value.source.code].append(value)

    for source in sources:
        row = existing.get(source.code)
        summary.sources.append(
            {
                "code": source.code,
                "file": source.mapping["source_reference"],
                "sha256": source.sha256,
                "rows_read": len(source.parsed.rows),
                "observations": len(source.parsed.observations),
                "already_imported": row is not None,
            }
        )
        if row is not None:
            summary.existing_batches += 1
            batches[source.code] = row
            continue
        summary.new_batches += 1
        batch = HistoricalImportBatch(
            id=uuid4(),
            batch_name=f"{source.code} v{source.mapping['version']}",
            original_filename=source.original_filename,
            source_reference=source.mapping["source_reference"],
            source_sha256=source.sha256,
            source_domain=source.mapping["domain"],
            mapping_code=source.code,
            mapping_version=source.mapping["version"],
            status=_batch_status(values_by_source[source.code]),
            notes=source.mapping.get("description"),
        )
        batches[source.code] = batch
        if commit:
            db.add(batch)
            db.flush()
            for number, raw in enumerate(source.parsed.rows, start=1):
                db.add(HistoricalSourceRow(id=uuid4(), batch_id=batch.id, row_number=number, raw_payload=raw))
            db.flush()

    periods: dict[PeriodKey, HistoricalPeriod] = {}
    source_row_ids: dict[tuple[UUID, int], UUID] = {}
    if commit:
        for batch_row in batches.values():
            for source_row in db.scalars(
                select(HistoricalSourceRow).where(HistoricalSourceRow.batch_id == batch_row.id)
            ):
                source_row_ids[(batch_row.id, source_row.row_number)] = source_row.id

    preview_values: dict[PeriodKey, dict[tuple[str, str], HistoricalMetricValue]] = defaultdict(dict)
    for value in plan.values:
        item = value.observation
        batch = batches[value.source.code]
        period = _period_row(db, periods, item.period, create=commit)
        candidate = HistoricalMetricValue(
            id=uuid4(),
            period_id=period.id,
            domain=item.domain,
            metric_code=item.metric_code,
            value_numeric=item.value,
            value_qualifier=item.qualifier,
            unit=item.unit,
            source_batch_id=batch.id,
            source_row_id=source_row_ids.get((batch.id, item.row_number)),
            source_column=item.source_column,
            verification_status=value.verification_status,
            authority_status=value.authority_status,
            version=1,
            notes=_notes(value),
            coverage_end_stated=value.coverage_end_stated,
        )
        if value.verification_status == "VERIFIED" and value.authority_status == "AUTHORITATIVE":
            preview_values[item.period][(item.domain, item.metric_code)] = candidate
        current = (
            _current_value(db, period.id, item.domain, item.metric_code, batch.id)
            if value.source.code in existing
            else None
        )
        if current is None:
            summary.inserted_values += 1
            if value.source.code in reinterpretations:
                _supersede_prior_interpretation(
                    db, reinterpretations[value.source.code], candidate, batch, period, summary, commit=commit
                )
            if commit:
                db.add(candidate)
        elif (
            current.value_numeric,
            current.verification_status,
            current.authority_status,
            current.coverage_end_stated,
        ) == (
            item.value,
            value.verification_status,
            value.authority_status,
            value.coverage_end_stated,
        ):
            summary.unchanged_values += 1
        else:
            # Reconciliation outcome changed (e.g. an owner resolution was added):
            # append a superseding version; the previous one stays traceable.
            summary.versioned_values += 1
            if commit:
                candidate.version = current.version + 1
                candidate.supersedes_id = current.id
                candidate.source_row_id = current.source_row_id
                db.add(candidate)
                if value.confirmation is not None:
                    _record_coverage_confirmation(db, value, current, candidate, batch, period, summary)
    if commit:
        db.flush()

    for conflict in plan.conflicts:
        period = _period_row(db, periods, conflict.period, create=commit)
        stored = db.scalar(select(HistoricalConflict).where(HistoricalConflict.conflict_key == conflict.key))
        if stored is None:
            summary.inserted_conflicts += 1
            if commit:
                db.add(
                    HistoricalConflict(
                        id=uuid4(),
                        conflict_key=conflict.key,
                        conflict_type=conflict.conflict_type,
                        domain=conflict.domain,
                        metric_code=conflict.metric_code,
                        period_id=period.id,
                        source_a_batch_id=batches[conflict.source_a].id,
                        value_a=conflict.value_a,
                        source_b_batch_id=batches[conflict.source_b].id if conflict.source_b else None,
                        value_b=conflict.value_b,
                        detail=conflict.detail,
                        resolution_status=conflict.resolution_status,
                        chosen_batch_id=batches[conflict.chosen_source].id if conflict.chosen_source else None,
                        resolution_reason=conflict.resolution_reason,
                        resolved_at=conflict.resolved_at,
                    )
                )
        elif stored.resolution_status == "UNRESOLVED" and conflict.resolution_status != "UNRESOLVED":
            summary.updated_conflicts += 1
            if commit:
                stored.resolution_status = conflict.resolution_status
                stored.chosen_batch_id = batches[conflict.chosen_source].id if conflict.chosen_source else None
                stored.resolution_reason = conflict.resolution_reason
                stored.resolved_at = conflict.resolved_at

    if commit:
        db.flush()
        summary.inserted_calculations, summary.unchanged_calculations = calculate_all(db)
    else:
        summary.calculations_preview = _preview_calculations(db, periods, preview_values)
    _compare_source_reported(db, plan, periods, batches, summary, commit=commit)
    return summary


def _compare_source_reported(
    db: Session,
    plan: ReconciliationPlan,
    periods: dict[PeriodKey, HistoricalPeriod],
    batches: dict[str, HistoricalImportBatch],
    summary: ImportSummary,
    *,
    commit: bool,
) -> None:
    """A source-reported result is never authoritative: the backend recalculates
    it independently, and any disagreement is a reconciliation conflict."""
    for value in plan.values:
        item = value.observation
        code = item.compare_to_calculation
        if not code:
            continue
        period = periods[item.period]
        calculated: Decimal | None = None
        if commit:
            row = db.scalar(
                select(HistoricalCalculationResult).where(
                    HistoricalCalculationResult.period_id == period.id,
                    HistoricalCalculationResult.calculation_code == code,
                    HistoricalCalculationResult.is_current.is_(True),
                )
            )
            calculated = row.result_value if row is not None else None
        else:
            preview = summary.calculations_preview.get(item.period.label, {}).get(code)
            calculated = Decimal(preview) if preview and not preview.startswith("unavailable") else None
        agrees = calculated is not None and precision_only_difference(calculated, item.value) is not None
        summary.comparisons.append(
            {
                "period": item.period.label,
                "calculation": code,
                "source_reported": f"{item.value.normalize():f}",
                "calculated": "unavailable" if calculated is None else f"{calculated.normalize():f}",
                "status": "match" if agrees else "CONFLICT",
            }
        )
        if agrees or not commit:
            continue
        batch = batches[value.source.code]
        key = "|".join(
            (
                "source_reported_vs_calculated",
                f"{period.granularity}|{period.coverage_start}|{period.coverage_end}",
                item.domain,
                code,
                batch.batch_name,
            )
        )
        if db.scalar(select(HistoricalConflict.id).where(HistoricalConflict.conflict_key == key)) is None:
            summary.inserted_conflicts += 1
            db.add(
                HistoricalConflict(
                    id=uuid4(),
                    conflict_key=key,
                    conflict_type="source_reported_vs_calculated",
                    domain=item.domain,
                    metric_code=code,
                    period_id=period.id,
                    source_a_batch_id=batch.id,
                    value_a=item.value,
                    value_b=calculated,
                    detail=(
                        f"{batch.batch_name} reports {code} = {item.value} ({item.source_column}); the governed "
                        f"backend calculation is {calculated if calculated is not None else 'unavailable'}"
                    ),
                )
            )
    if commit:
        db.flush()


def _preview_calculations(
    db: Session,
    periods: dict[PeriodKey, HistoricalPeriod],
    values: dict[PeriodKey, dict[tuple[str, str], HistoricalMetricValue]],
) -> dict[str, dict[str, str]]:
    populations: dict[int, tuple[Decimal | None, dict[str, object]]] = {}
    for key, metrics in values.items():
        if key.granularity == "ANNUAL" and ("population", "population") in metrics:
            populations[key.year] = (
                metrics[("population", "population")].value_numeric,
                {"kind": "historical_verified (planned)", "effective_year": key.year},
            )
    preview: dict[str, dict[str, str]] = {}
    for key in sorted(periods, key=lambda item: (item.coverage_start, item.granularity)):
        from app.historical.calculator import population_for

        governed = population_for(db, key.year)
        population = (
            governed
            if governed[0] is not None and governed[1]["kind"] == "governed_population_reference"
            else populations.get(key.year, (None, {"kind": "unavailable"}))
        )
        calculator = PeriodCalculator(db, periods[key], values=values.get(key, {}), population=population)
        calculator.calculate()
        if calculator.results:
            preview[key.label] = {
                code: (
                    str(result[0].quantize(Decimal("0.000001")))
                    if result[0] is not None
                    else f"unavailable ({result[1]})"
                )
                for code, result in sorted(calculator.results.items())
            }
    return preview


def render_report(
    sources: list[LoadedSource], plan: ReconciliationPlan, summary: ImportSummary, *, commit: bool
) -> str:
    lines = [f"# Historical import {'commit' if commit else 'dry run'}", ""]
    if not commit:
        lines += ["Dry run: the database was only read. Nothing was inserted, updated or deleted.", ""]
    lines += [
        "## Sources",
        "",
        "| Mapping | File | SHA-256 | Rows read | Observations | Already imported |",
        "|---|---|---|---|---|---|",
    ]
    for item in summary.sources:
        lines.append(
            f"| {item['code']} | `{item['file']}` | `{item['sha256']}` | {item['rows_read']} | "
            f"{item['observations']} | {'yes' if item['already_imported'] else 'no'} |"
        )
    lines += ["", "## Periods, granularity and metrics", ""]
    for source in sources:
        observations = source.parsed.observations
        periods = Counter(f"{item.period.granularity} {item.period.label}" for item in observations)
        metrics = sorted({item.metric_code for item in observations})
        conversions = sorted({f"{item.metric_code}: {item.unit}" for item in observations})
        lines += [
            f"### {source.code}",
            "",
            f"- Periods detected ({len(periods)}): " + ", ".join(sorted(periods)),
            f"- Metrics mapped ({len(metrics)}): " + ", ".join(metrics),
            "- Units (no unit conversion applied; source units are canonical units): " + ", ".join(conversions),
            f"- Ignored: {'; '.join(source.parsed.ignored) or 'none'}",
            f"- Invalid rows: {'; '.join(source.parsed.invalid) or 'none'}",
            f"- Qualifiers: {dict(Counter(item.qualifier for item in observations))}",
        ]
        checks = source.parsed.checks
        lines.append(f"- Internal checks: {sum(check.passed for check in checks)}/{len(checks)} passed")
        for check in checks:
            if not check.passed:
                kind = "ADVISORY (quality note only)" if check.advisory else "FAILED"
                lines.append(f"  - {kind}: {check.description} (printed {check.expected}, computed {check.actual})")
        lines.append("")
    status = Counter((value.verification_status, value.authority_status) for value in plan.values)
    lines += ["## Reconciliation outcome", "", "| Verification | Authority | Values |", "|---|---|---|"]
    lines += [f"| {key[0]} | {key[1]} | {count} |" for key, count in sorted(status.items())]
    lines += ["", f"Precision-only differences auto-resolved (rule R1): {len(plan.auto_resolutions)}"]
    lines += [f"- {item}" for item in plan.auto_resolutions]
    lines += [
        "",
        "## Conflicts",
        "",
        "| Type | Period | Metric | Source A | Value A | Source B | Value B | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for conflict in plan.conflicts:
        lines.append(
            f"| {conflict.conflict_type} | {conflict.period.label} | {conflict.domain}.{conflict.metric_code} | "
            f"{conflict.source_a} | {conflict.value_a} | {conflict.source_b or '(computed)'} | "
            f"{conflict.value_b} | {conflict.resolution_status} |"
        )
    if summary.reinterpreted:
        lines += ["", "## Unit reinterpretations (owner-approved; numbers unchanged)", ""]
        lines += ["| Period | Superseded interpretation | Corrected interpretation |", "|---|---|---|"]
        lines += [f"| {item['period']} | {item['from']} | {item['to']} |" for item in summary.reinterpreted]
    if summary.comparisons:
        lines += ["", "## Source-reported results vs governed backend calculation", ""]
        lines += ["| Period | Calculation | Source reported | Backend calculated | Status |", "|---|---|---|---|---|"]
        lines += [
            f"| {item['period']} | {item['calculation']} | {item['source_reported']} | {item['calculated']} | "
            f"{item['status']} |"
            for item in summary.comparisons
        ]
    lines += [
        "",
        "## Records",
        "",
        f"- New batches: {summary.new_batches}; already imported: {summary.existing_batches}",
        f"- Metric values to insert: {summary.inserted_values}; new versions: {summary.versioned_values}; "
        f"unchanged (skipped): {summary.unchanged_values}",
        f"- Conflicts to insert: {summary.inserted_conflicts}; resolutions to record: {summary.updated_conflicts}",
    ]
    if commit:
        lines.append(
            f"- Calculations inserted: {summary.inserted_calculations}; unchanged: {summary.unchanged_calculations}"
        )
    else:
        lines += ["", "## Calculated indicators (preview from authoritative values only)", ""]
        for label, results in summary.calculations_preview.items():
            lines.append(f"### {label}")
            lines += [f"- {code}: {value}" for code, value in results.items()]
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", required=True, type=Path, help="repository root holding the source files")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--only", action="append", help="limit to mapping code(s)")
    parser.add_argument("--report", type=Path, help="write the markdown report here")
    parser.add_argument("--database-url", help="defaults to the configured DATABASE_URL")
    args = parser.parse_args(argv)

    mappings = load_mappings(only=set(args.only) if args.only else None)
    sources = load_sources(args.source_root, mappings)
    plan = reconcile(sources, load_resolutions(), load_coverage_confirmations())
    engine = create_engine(args.database_url or Settings().DATABASE_URL)
    with Session(engine) as db:
        try:
            summary = run(db, sources, plan, commit=args.commit)
            if args.commit:
                db.commit()
            else:
                db.rollback()
        except ImportRefused as exc:
            db.rollback()
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
    report = render_report(sources, plan, summary, commit=args.commit)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
