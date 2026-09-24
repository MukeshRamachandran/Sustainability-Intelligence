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
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.historical.calculator import PeriodCalculator, calculate_all
from app.historical.sources import PeriodKey, parse_source, sha256_bytes
from app.historical.validator import LoadedSource, PlannedValue, ReconciliationPlan, reconcile
from app.models.history import (
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


def run(db: Session, sources: list[LoadedSource], plan: ReconciliationPlan, *, commit: bool) -> ImportSummary:
    summary = ImportSummary()
    existing = _existing_batches(db, sources)
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
            if commit:
                db.add(candidate)
        elif (current.value_numeric, current.verification_status, current.authority_status) == (
            item.value,
            value.verification_status,
            value.authority_status,
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
    return summary


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
                lines.append(f"  - FAILED: {check.description} (printed {check.expected}, computed {check.actual})")
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
    plan = reconcile(sources, load_resolutions())
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
