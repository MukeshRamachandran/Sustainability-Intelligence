"""Reconcile observations from every source copy before anything is stored.

Rules (documented in HISTORICAL_DATA_ARCHITECTURE.md):

R0  A failed internal source check marks the affected values CONFLICT.
R1  Copies agree when their values are equal, or when one is exactly the
    other rounded to fewer decimal places (a precision-only difference); the
    more precise value is kept and the difference is recorded as RESOLVED.
R2  Copies that genuinely disagree are all marked CONFLICT and recorded as
    UNRESOLVED - unless an owner-approved entry in resolutions.json selects
    one source, which then becomes AUTHORITATIVE and the others REJECTED.
R3  A reported ANNUAL/YTD aggregate is compared with the sum of the genuine
    monthly values it covers. A mismatch is a CONFLICT for the aggregate and
    for the monthly values of the same metric, unless the aggregate's own
    source declares itself superseded by monthly rows (REJECTED_SOURCE).
R4  A value whose source does not state its coverage stays UNVERIFIED.
R5  Only VERIFIED values from the highest-priority agreeing source become
    AUTHORITATIVE; agreeing lower-priority copies stay SOURCE_REPORTED.
    A reference-only value (mapping ``reference_only``) is never AUTHORITATIVE.
An advisory internal check (``advisory``) never blocks: a failure becomes a
quality note on the affected values, which keep their verification status.
C1  An owner-approved coverage confirmation (resolutions.json
    ``coverage_confirmations``) turns a value that R4 left UNVERIFIED into a
    VERIFIED one. When the source does not state the end month, the value
    keeps ``coverage_end_stated = False`` so it is never shown with a guessed
    month range. CONFLICT and REJECTED values are never confirmed this way.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.historical.sources import Observation, ParsedSource, PeriodKey

R1_REASON = "Rule R1: the values differ only by rounding; the more precise value is kept."


@dataclass
class LoadedSource:
    mapping: dict[str, Any]
    parsed: ParsedSource
    sha256: str
    original_filename: str

    @property
    def code(self) -> str:
        return str(self.mapping["code"])

    @property
    def priority(self) -> int:
        return int(self.mapping["priority"])


@dataclass
class PlannedValue:
    source: LoadedSource
    observation: Observation
    verification_status: str = "VERIFIED"
    authority_status: str = "SOURCE_REPORTED"
    notes: list[str] = field(default_factory=list)
    coverage_end_stated: bool = True
    # The owner-approved coverage confirmation applied to this value (C1), if any.
    confirmation: dict[str, Any] | None = None

    @property
    def key(self) -> tuple[PeriodKey, str, str]:
        return (self.observation.period, self.observation.domain, self.observation.metric_code)


@dataclass
class PlannedConflict:
    conflict_type: str
    period: PeriodKey
    domain: str
    metric_code: str
    source_a: str
    value_a: Decimal | None
    source_b: str | None
    value_b: Decimal | None
    detail: str
    resolution_status: str = "UNRESOLVED"
    chosen_source: str | None = None
    resolution_reason: str | None = None
    resolved_at: datetime | None = None

    @property
    def key(self) -> str:
        period = f"{self.period.granularity}|{self.period.coverage_start}|{self.period.coverage_end}"
        return "|".join(
            (self.conflict_type, period, self.domain, self.metric_code, self.source_a, self.source_b or "-")
        )


@dataclass
class ReconciliationPlan:
    values: list[PlannedValue]
    conflicts: list[PlannedConflict]
    auto_resolutions: list[str]


def _decimals(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def precision_only_difference(a: Decimal, b: Decimal) -> Decimal | None:
    """Return the more precise value when a and b differ only by rounding."""
    if a == b:
        return a
    precise, coarse = (a, b) if _decimals(a) > _decimals(b) else (b, a)
    if _decimals(precise) == _decimals(coarse):
        return None
    quantum = Decimal(1).scaleb(-_decimals(coarse))
    return precise if precise.quantize(quantum) == coarse else None


def _resolution_index(resolutions: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    index = {}
    for entry in resolutions:
        for required in (
            "granularity",
            "coverage_start",
            "coverage_end",
            "domain",
            "metric_code",
            "chosen_mapping_code",
            "reason",
            "approved_by",
            "approved_at",
        ):
            if not entry.get(required):
                raise ValueError(f"resolution entry is missing {required!r}: {entry}")
        index[
            (
                entry["granularity"],
                entry["coverage_start"],
                entry["coverage_end"],
                entry["domain"],
                entry["metric_code"],
            )
        ] = entry
    return index


COVERAGE_CONFIRMATION_FIELDS = (
    "id",
    "mapping_code",
    "granularity",
    "coverage_start",
    "coverage_end",
    "domain",
    "metric_codes",
    "reason",
    "approved_by",
    "approved_at",
)


def _confirmation_index(
    confirmations: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str, str, str], dict[str, Any]]:
    index = {}
    for entry in confirmations:
        missing = [name for name in COVERAGE_CONFIRMATION_FIELDS if entry.get(name) in (None, "", [])]
        if missing or not isinstance(entry.get("coverage_end_stated"), bool):
            raise ValueError(f"coverage confirmation is missing {missing or ['coverage_end_stated']}: {entry}")
        for metric in entry["metric_codes"]:
            index[
                (
                    entry["mapping_code"],
                    entry["granularity"],
                    entry["coverage_start"],
                    entry["coverage_end"],
                    entry["domain"],
                    metric,
                )
            ] = entry
    return index


def _apply_coverage_confirmations(
    planned: list[PlannedValue], confirmations: list[dict[str, Any]]
) -> None:
    index = _confirmation_index(confirmations)
    for value in planned:
        period = value.observation.period
        entry = index.get(
            (
                value.source.code,
                period.granularity,
                period.coverage_start.isoformat(),
                period.coverage_end.isoformat(),
                value.observation.domain,
                value.observation.metric_code,
            )
        )
        if entry is None or value.verification_status != "UNVERIFIED":
            continue
        value.verification_status = "VERIFIED"
        value.coverage_end_stated = entry["coverage_end_stated"]
        value.confirmation = entry
        value.notes.append(
            f"coverage confirmed by owner ({entry['id']}, {entry['approved_by']}, {entry['approved_at']})"
            + ("" if entry["coverage_end_stated"] else "; coverage end month not stated in the source")
        )


def reconcile(
    sources: list[LoadedSource],
    resolutions: list[dict[str, Any]],
    coverage_confirmations: list[dict[str, Any]] | None = None,
) -> ReconciliationPlan:
    now = datetime.now(UTC)
    resolved = _resolution_index(resolutions)
    planned = [
        PlannedValue(source, item, verification_status=item.verification_hint, notes=list(item.notes))
        for source in sources
        for item in source.parsed.observations
    ]
    conflicts: list[PlannedConflict] = []
    auto: list[str] = []
    by_key: dict[tuple[PeriodKey, str, str], list[PlannedValue]] = defaultdict(list)
    for value in planned:
        by_key[value.key].append(value)

    def mark(value: PlannedValue, note: str) -> None:
        if value.verification_status != "REJECTED":
            value.verification_status = "CONFLICT"
        value.notes.append(note)

    # R0 - internal source checks.
    for source in sources:
        for check in source.parsed.checks:
            if check.passed:
                continue
            if check.advisory:
                note = (
                    f"quality note (advisory, not used in any calculation): {check.description}: "
                    f"source states {check.expected}, arithmetic gives {check.actual}"
                )
                for period, domain, metric in check.affects:
                    for value in by_key.get((period, domain, metric), []):
                        if value.source is source:
                            value.notes.append(note)
                continue
            for period, domain, metric in check.affects:
                for value in by_key.get((period, domain, metric), []):
                    if value.source is source:
                        mark(value, f"internal check failed: {check.description}")
                conflicts.append(
                    PlannedConflict(
                        "internal_inconsistency",
                        period,
                        domain,
                        metric,
                        source.code,
                        check.expected,
                        None,
                        check.actual,
                        f"{check.description}: printed {check.expected}, computed {check.actual}",
                    )
                )

    # R1 / R2 - competing copies of the same value.
    for key, values in by_key.items():
        batches = {value.source.code for value in values}
        if len(batches) < 2:
            continue
        values.sort(key=lambda item: item.source.priority)
        primary = values[0]
        disagreeing = []
        for other in values[1:]:
            kept = precision_only_difference(primary.observation.value, other.observation.value)
            if kept is None:
                disagreeing.append(other)
            elif primary.observation.value != other.observation.value:
                conflicts.append(
                    PlannedConflict(
                        "precision_difference",
                        key[0],
                        key[1],
                        key[2],
                        primary.source.code,
                        primary.observation.value,
                        other.source.code,
                        other.observation.value,
                        "copies differ only by rounding precision",
                        resolution_status="RESOLVED",
                        chosen_source=primary.source.code if kept == primary.observation.value else other.source.code,
                        resolution_reason=R1_REASON,
                        resolved_at=now,
                    )
                )
                auto.append(f"{key[0].label} {key[2]}: {primary.observation.value} vs {other.observation.value} (R1)")
                if kept != primary.observation.value:
                    other.notes.append("R1: more precise copy selected")
                    values.remove(other)
                    values.insert(0, other)
                    primary = other
        if not disagreeing:
            continue
        period = key[0]
        resolution = resolved.get(
            (period.granularity, period.coverage_start.isoformat(), period.coverage_end.isoformat(), key[1], key[2])
        )
        for other in disagreeing:
            conflict = PlannedConflict(
                "source_copies_disagree",
                period,
                key[1],
                key[2],
                primary.source.code,
                primary.observation.value,
                other.source.code,
                other.observation.value,
                f"{primary.source.code}={primary.observation.value} vs {other.source.code}={other.observation.value}",
            )
            if resolution is not None:
                conflict.resolution_status = "RESOLVED"
                conflict.chosen_source = resolution["chosen_mapping_code"]
                conflict.resolution_reason = (
                    f"{resolution['reason']} (approved by {resolution['approved_by']} on {resolution['approved_at']})"
                )
                conflict.resolved_at = now
            conflicts.append(conflict)
        for value in values:
            if resolution is None:
                mark(value, "competing source copies disagree (unresolved)")
            elif value.source.code == resolution["chosen_mapping_code"]:
                value.notes.append("selected by owner-approved resolution")
            else:
                value.verification_status = "REJECTED"
                value.notes.append("rejected by owner-approved resolution")

    # R3 - reported aggregates versus the genuine monthly values they cover.
    def monthly_value(year: int, month: int, domain: str, metric: str) -> tuple[Decimal | None, bool]:
        candidates = [
            value
            for value in by_key.get((PeriodKey.monthly(year, month), domain, metric), [])
            if value.verification_status in ("VERIFIED", "CONFLICT")
        ]
        if not candidates:
            return None, False
        best = min(candidates, key=lambda item: item.source.priority)
        return best.observation.value, best.verification_status == "CONFLICT"

    for value in planned:
        against = value.observation.reconcile_against
        period = value.observation.period
        if not against or period.granularity == "MONTHLY" or value.observation.qualifier != "EXACT":
            continue
        total = Decimal("0")
        complete, contested = True, False
        for year, month in period.months():
            for metric in against:
                item, is_conflict = monthly_value(year, month, value.observation.domain, metric)
                if item is None:
                    complete = False
                else:
                    total += item
                    contested = contested or is_conflict
        if not complete or total == value.observation.value:
            continue
        detail = (
            f"reported {period.label} {value.observation.metric_code} = {value.observation.value}; "
            f"sum of monthly {' + '.join(against)} = {total}"
        )
        superseded = value.source.mapping.get("superseded_by_monthly_rows")
        conflict = PlannedConflict(
            "aggregate_vs_monthly",
            period,
            value.observation.domain,
            value.observation.metric_code,
            value.source.code,
            value.observation.value,
            None,
            total,
            detail,
        )
        resolution = resolved.get(
            (
                period.granularity,
                period.coverage_start.isoformat(),
                period.coverage_end.isoformat(),
                value.observation.domain,
                value.observation.metric_code,
            )
        )
        if superseded:
            value.verification_status = "REJECTED"
            value.notes.append(f"rejected: {superseded}")
            conflict.resolution_status = "REJECTED_SOURCE"
            conflict.resolution_reason = superseded
            conflict.resolved_at = now
        elif resolution is not None and resolution["chosen_mapping_code"] == value.source.code:
            # Owner-approved: the reported aggregate is the authoritative figure.
            # The monthly values it contradicts are rejected for this metric -
            # never published, never summed; the aggregate is never split.
            value.notes.append("selected by owner-approved resolution")
            if tuple(against) == (value.observation.metric_code,):
                for year, month in period.months():
                    for monthly in by_key.get(
                        (PeriodKey.monthly(year, month), value.observation.domain, value.observation.metric_code), []
                    ):
                        monthly.verification_status = "REJECTED"
                        monthly.notes.append(f"rejected by owner-approved {period.label} resolution")
            conflict.resolution_status = "RESOLVED"
            conflict.chosen_source = value.source.code
            conflict.resolution_reason = (
                f"{resolution['reason']} (approved by {resolution['approved_by']} on {resolution['approved_at']})"
            )
            conflict.resolved_at = now
        else:
            mark(value, "reported aggregate does not equal the sum of its monthly values")
            if tuple(against) == (value.observation.metric_code,):
                for year, month in period.months():
                    for monthly in by_key.get(
                        (PeriodKey.monthly(year, month), value.observation.domain, value.observation.metric_code), []
                    ):
                        mark(monthly, f"monthly values do not reconcile with the reported {period.label} total")
            if contested:
                conflict.detail += " (some monthly values are themselves contested)"
        conflicts.append(conflict)

    # C1 - owner-confirmed coverage, then R4 / R5 - authority.
    _apply_coverage_confirmations(planned, coverage_confirmations or [])
    for values in by_key.values():
        verified = [
            value
            for value in values
            if value.verification_status == "VERIFIED" and not value.observation.reference_only
        ]
        if not verified:
            continue
        chosen = min(verified, key=lambda item: item.source.priority)
        chosen.authority_status = "AUTHORITATIVE"
    return ReconciliationPlan(planned, conflicts, auto)
