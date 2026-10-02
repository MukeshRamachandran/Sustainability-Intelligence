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

GHG totals (Scope 1, Scope 2, Operational GHG and its per-capita value) follow
the owner-approved available-data methodology: they are the sum of whatever
verified contributors exist. Each carries ``calculation_status`` (COMPLETE /
PARTIAL), the contributors that produced it and the ones that are missing, so
a partial figure is never presented as a complete one. A missing contributor
or month is excluded, never counted as zero.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.historical.calculator import (
    COMPLETE,
    CONTRIBUTOR_LABELS,
    GHG_TOTAL_CONTRIBUTORS,
    GRID_EMISSIONS,
    PARTIAL,
    PER_CAPITA_GHG,
    SCOPE1_CONTRIBUTORS,
    current_authoritative_values,
    ghg_completeness,
    population_for,
)
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
    # A calculation only for kWh-methodology periods (litres derived from DG
    # generation); in legacy periods the same code is a source-reported metric.
    "dg_diesel_litres": "transport",
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
    "waste_diverted_from_landfill_kg": "waste",
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
# Units of the outreach totals a published release carries (the same units the
# historical outreach sources use, so like is only ever added to like).
OUTREACH_METRIC_UNITS = {
    "total_programs": "programmes",
    "total_participants": "people",
    "partner_organizations": "organizations",
    "saplings_planted": "saplings",
    "experts_involved": "people",
    "volunteers_engaged": "people",
    "volunteer_hours": "hours",
}
# A distinct count: organisations in a later month may already be in a
# cumulative baseline, so adding months to it could overstate the total.
BASELINE_NOT_EXTENDED = {"partner_organizations"}
RUNNING_YTD = "ytd_baseline_plus_later_months"
# Current-year KPIs whose month view prefers year-to-date context over annual
# context, and whose partial monthly sums are labelled with their real months.
CURRENT_YEAR_KPI_CODES = {"water_recycled_kl", "total_waste_generated_kg"}
# Waste is a year-aggregate domain: one running figure per year (a historical
# Annual/YTD baseline plus the published months after it), shown for every
# selection inside that year.
WASTE_YEAR_AGGREGATE = "waste_year_aggregate"
WASTE_WET = "wet_waste_generated_kg"
WASTE_DRY = "dry_waste_generated_kg"
WASTE_TOTAL = "total_waste_generated_kg"
WASTE_DIVERTED = "waste_diverted_from_landfill_kg"
WASTE_PER_CAPITA = "waste_per_capita_kg"
WASTE_RECOMPUTED = (WASTE_TOTAL, WASTE_DIVERTED, WASTE_PER_CAPITA)
DISPLAY_PLACES = {
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
    # False for an owner-confirmed "<year> / to date" figure whose source does
    # not state the end month; ``coverage_label`` is then its only public
    # coverage (for example "2026 YTD"), never a guessed month range.
    end_stated: bool = True
    coverage_label: str | None = None
    # GHG totals only: COMPLETE / PARTIAL, what contributed and what is missing.
    # DG activity only: SOURCE_REPORTED_LITRES (legacy) or DERIVED_FROM_KWH.
    activity_origin: str | None = None
    calculation_status: str | None = None
    contributors: list[dict[str, Any]] = field(default_factory=list)
    missing_contributors: list[dict[str, Any]] = field(default_factory=list)

    def completeness_json(self) -> dict[str, Any]:
        if self.calculation_status is None:
            return {}
        if self.value is None:
            return {"calculation_status": "UNAVAILABLE", "contributors": [], "missing_contributors": []}
        return {
            "calculation_status": self.calculation_status,
            "contributors": self.contributors,
            "missing_contributors": self.missing_contributors,
        }

    def origin_json(self) -> dict[str, Any]:
        return {} if self.activity_origin is None else {"activity_origin": self.activity_origin}

    def as_json(self) -> dict[str, Any]:
        return {
            **self.completeness_json(),
            **self.origin_json(),
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
            "coverage_label": self.coverage_label,
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
                derivation = item.get("derivation")
                if isinstance(derivation, dict) and derivation.get("derived_metric_code"):
                    # kWh-based DG: the release froze the derived litres with the result.
                    entry.values[item["calculation_code"]].provenance["derivation"] = derivation
                    put(
                        str(derivation["derived_metric_code"]),
                        domain,
                        "calculation",
                        derivation.get("derived_value"),
                        str(derivation.get("derived_unit") or ""),
                    )
                    entry.values[str(derivation["derived_metric_code"])].provenance = {
                        **provenance,
                        "derivation": derivation,
                    }
        if domain == "waste":
            for material in block.get("materials") or []:
                put(f"material:{material['code']}", "waste", "metric", material.get("quantity_kg"), "kg")
    outreach = payload.get("outreach")
    if isinstance(outreach, dict):
        for code, unit in OUTREACH_METRIC_UNITS.items():
            put(code, "outreach", "metric", outreach.get(code), unit)
        for theme, count in (outreach.get("themes") or {}).items():
            put(f"theme:{theme}", "outreach", "metric", count, "programmes")
        for category, count in (outreach.get("participants_by_category") or {}).items():
            put(f"audience:{category}", "outreach", "metric", count, "people")
        # A legacy release payload may still carry a "gender" block. Outreach is
        # no longer reported by gender, so it is not read, aggregated or exposed.
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
    dry = entry.values.get(WASTE_DRY)
    if dry is not None and dry.value is not None and _available(entry, WASTE_DIVERTED) is None:
        # Releases frozen before the diverted indicator existed: the governed
        # rule (diverted = dry waste) is applied to the published dry figure.
        put(WASTE_DIVERTED, "waste", "calculation", formulas.waste_diverted_from_landfill_kg(dry.value), dry.unit)
    population = payload.get("population")
    if isinstance(population, dict):
        entry.population = {key: population.get(key) for key in ("status", "value", "unit", "effective_year")}
    # A published total was prepared under the strict release rule and is shown
    # exactly as published; its contributors are the release's own results.
    _mark_dg_origin(entry)
    emissions = {code: _available(entry, code) for code in (*SCOPE1_CONTRIBUTORS, GRID_EMISSIONS)}
    for code, meta in ghg_completeness(emissions, None).items():
        _apply_completeness(entry.values.get(code), meta)
    _copy_completeness(entry.values.get("operational_ghg_tco2e"), entry.values.get(PER_CAPITA_GHG))
    return entry


def _available(entry: Entry, code: str) -> Decimal | None:
    item = entry.values.get(code)
    return item.value if item is not None else None


def _public_contributors(items: Any) -> list[dict[str, Any]]:
    """Stored contributor values are canonical text; the API publishes numbers."""
    result = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        public = dict(item)
        if "value" in public:
            public["value"] = _number(Decimal(str(public["value"])), str(public.get("code")))
        result.append(public)
    return result


def _apply_completeness(value: Value | None, meta: Any) -> None:
    if value is None or not isinstance(meta, dict) or not meta.get("status"):
        return
    value.calculation_status = str(meta["status"])
    value.contributors = _public_contributors(meta.get("contributors"))
    value.missing_contributors = _public_contributors(meta.get("missing_contributors"))


def _copy_completeness(source: Value | None, target: Value | None) -> None:
    if source is None or target is None or source.calculation_status is None:
        return
    target.calculation_status = source.calculation_status
    target.contributors = source.contributors
    target.missing_contributors = source.missing_contributors


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
        stated = row.coverage_end_stated
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
                **({} if stated else {"coverage_end_stated": False}),
            },
            end_stated=stated,
            coverage_label=None if stated else f"{period.year} {period.granularity}",
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
        _apply_completeness(entry.values[calc.calculation_code], calc.provenance.get("completeness"))
        derivation = calc.provenance.get("derivation")
        if isinstance(derivation, dict):
            entry.values[calc.calculation_code].provenance["derivation"] = derivation
    _mark_dg_origin(entry)
    return entry


DG_ACTIVITY_CODES = ("dg_diesel_litres", "dg_diesel_emissions")


def _mark_dg_origin(entry: Entry) -> None:
    """State which DG pathway a period used: derived from kWh, or source-reported litres.

    Read from the stored derivation; nothing is converted here, and a legacy
    period never gains an invented kWh value.
    """
    for code in DG_ACTIVITY_CODES:
        value = entry.values.get(code)
        if value is None or value.value is None:
            continue
        derivation = value.provenance.get("derivation")
        value.activity_origin = (
            str(derivation.get("activity_origin")) if isinstance(derivation, dict) else "SOURCE_REPORTED_LITRES"
        )


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
        # Available-data rule: any Operational GHG value (complete or partial)
        # with a valid population; its completeness is copied below.
        PER_CAPITA_GHG: (
            "ghg",
            "kgCO2e/person",
            formulas.operational_ghg_per_capita_kgco2e(_available(entry, "operational_ghg_tco2e"), population),
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
        if code == PER_CAPITA_GHG and derived_value is None:
            reason = "operational_ghg_or_population_unavailable"
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
        operational = entry.values.get("operational_ghg_tco2e")
        if code == PER_CAPITA_GHG and derived_value is not None and operational is not None:
            entry.values[code].coverage_status = operational.coverage_status
            entry.values[code].months_covered = operational.months_covered
            _copy_completeness(operational, entry.values[code])


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
            calculation_status=value.calculation_status,
            contributors=value.contributors,
            missing_contributors=value.missing_contributors,
        )
    _derive_ratios(db, entry)
    return entry


def _waste_values(entry: Entry) -> dict[str, Value]:
    return {code: item for code, item in entry.values.items() if item.domain == "waste" and item.value is not None}


def _waste_year_aggregate(
    db: Session, year: int, months: list[Entry], sources: list[Entry]
) -> tuple[dict[str, Value], date, bool] | None:
    """The year's running Waste figure: newest baseline + the months after it.

    * Baseline: the verified Annual/YTD source that starts on 1 January and
      reaches furthest into the year. An older, shorter baseline is superseded
      by it and is not added.
    * Months: genuine monthly waste (a published release, or verified monthly
      history) is added only when the month STARTS after the baseline's end, so
      nothing inside the baseline's coverage is counted twice. Without a
      baseline every such month counts.
    * Wet, dry and each material are summed by code; total (wet + dry),
      diverted from landfill (= dry) and per person (total / population) are
      recomputed from those sums with the shared formulas.

    Nothing is split into months. The waste values are lifted out of the
    sources they came from so they appear once, in the year's aggregate view.
    Returns (values, coverage end, reaches 31 December) or None when the year
    has no waste baseline and no monthly waste.
    """
    start = date(year, 1, 1)
    candidates = [
        source
        for source in sources
        if source.coverage_start == start and any(item.end_stated for item in _waste_values(source).values())
    ]
    baseline = max(candidates, key=lambda item: (item.coverage_end, item.granularity == "ANNUAL"), default=None)
    reporting = [month for month in months if _waste_values(month)]
    later = [month for month in reporting if baseline is None or month.coverage_start > baseline.coverage_end]
    if baseline is None and not later:
        return None
    contributors = ([baseline] if baseline is not None else []) + later
    parts = [_waste_values(item) for item in contributors]
    for source in candidates:
        for code in [code for code, item in source.values.items() if item.domain == "waste"]:
            source.values.pop(code)

    def month_end(month: int) -> date:
        return date(year, month, calendar.monthrange(year, month)[1])

    # Coverage is contiguous from 1 January: the baseline, then each next month.
    reached = 0
    if baseline is not None:
        end = baseline.coverage_end
        reached = end.month if end == month_end(end.month) else -1
    added_months = {month.month for month in later}
    while 0 <= reached < 12 and reached + 1 in added_months:
        reached += 1
    full_year = reached == 12
    coverage_end = max(item.coverage_end for item in contributors)
    label = f"{year} Full Year" if full_year else f"{year} YTD"
    kinds = {month.source_kind for month in later}
    if baseline is not None:
        source_kind = "mixed_aggregate" if later else "historical_verified"
    else:
        source_kind = "published_release_aggregate" if kinds == {"published_release"} else "historical_aggregate"
    shared: dict[str, Any] = {
        "aggregation": WASTE_YEAR_AGGREGATE,
        "coverage_start": start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "months_added": [month.key for month in later],
        "months_excluded_overlap": [month.key for month in reporting if month not in later],
    }
    if baseline is not None:
        shared.update(
            {
                "baseline_granularity": baseline.granularity,
                "baseline_coverage_start": baseline.coverage_start.isoformat(),
                "baseline_coverage_end": baseline.coverage_end.isoformat(),
                "baselines_superseded": [
                    f"{item.coverage_start.isoformat()}..{item.coverage_end.isoformat()}"
                    for item in candidates
                    if item is not baseline
                ],
            }
        )

    def build(
        code: str, kind: str, amount: Decimal | None, unit: str, qualifiers: set[str], provenance: dict[str, Any],
        *, complete: bool = True, reason: str | None = None,
    ) -> Value:
        return Value(
            code,
            "waste",
            kind,
            amount,
            unit,
            reason,
            qualifier="EXACT" if qualifiers <= {"EXACT"} else "APPROXIMATE",
            source_kind=source_kind,
            granularity="ANNUAL" if full_year else "YTD",
            coverage_status="complete" if complete else "partial",
            months_covered=[month.key for month in later],
            provenance={**provenance, **shared},
            coverage_label=label,
        )

    values: dict[str, Value] = {}
    for code in sorted({code for part in parts for code in part} - set(WASTE_RECOMPUTED)):
        items = [part[code] for part in parts if code in part]
        own = parts[0].get(code) if baseline is not None else None
        provenance = dict(own.provenance) if own is not None else {}
        if own is not None:
            provenance["baseline_value"] = _number(own.value, code)
        values[code] = build(
            code,
            items[0].kind if len(parts) == 1 else "metric",
            sum((item.value for item in items if item.value is not None), Decimal("0")),
            items[0].unit,
            {item.qualifier for item in items},
            provenance,
            # A material missing from a contributor was simply not reported there.
            complete=code.startswith("material:") or len(items) == len(parts),
        )

    def complete(code: str) -> Value | None:
        item = values.get(code)
        return item if item is not None and item.coverage_status == "complete" else None

    wet, dry = complete(WASTE_WET), complete(WASTE_DRY)
    total = formulas.waste_total_kg(wet.value if wet else None, dry.value if dry else None)
    total_formula = f"{WASTE_WET} + {WASTE_DRY}"
    total_qualifiers = {item.qualifier for item in (wet, dry) if item is not None}
    if total is None and all(WASTE_TOTAL in part for part in parts):
        # No wet/dry split anywhere in the year: the contributors' own totals.
        totals = [part[WASTE_TOTAL] for part in parts]
        total = sum((item.value for item in totals if item.value is not None), Decimal("0"))
        total_formula = "sum of the reported totals"
        total_qualifiers = {item.qualifier for item in totals}
    values[WASTE_TOTAL] = build(
        WASTE_TOTAL, "calculation", total, "kg", total_qualifiers, {"formula": total_formula},
        reason=None if total is not None else "requires_wet_and_dry_waste",
    )
    diverted = formulas.waste_diverted_from_landfill_kg(dry.value if dry else None)
    values[WASTE_DIVERTED] = build(
        WASTE_DIVERTED, "calculation", diverted, "kg", {dry.qualifier} if dry else set(),
        {"formula": f"{WASTE_DRY} (owner-approved: dry waste is the waste diverted from landfill)"},
        reason=None if diverted is not None else "dry_waste_unavailable",
    )
    population, population_source = population_for(db, year)
    per_person = formulas.waste_per_capita_kg(total, population)
    values[WASTE_PER_CAPITA] = build(
        WASTE_PER_CAPITA, "calculation", per_person, "kg/person", total_qualifiers,
        {
            "formula": f"{WASTE_TOTAL} / population",
            "population": _number(population, "population"),
            "population_source_kind": population_source.get("kind"),
        },
        reason=None if per_person is not None else "requires_total_waste_and_population",
    )
    return values, coverage_end, full_year


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
    # Owner-confirmed year-to-date figures whose end month is not stated have no
    # trustworthy window of their own: they are lifted out of their stored
    # placeholder period and offered only as the year's YTD value (below).
    open_ended: dict[str, Value] = {}
    for source in sources:
        for code, value in list(source.values.items()):
            if not value.end_stated and value.value is not None:
                open_ended[code] = source.values.pop(code)
    waste_year = _waste_year_aggregate(db, year, months, sources)
    if waste_year is not None:
        # A dated waste aggregate exists: an undated figure is never added to it.
        for code in [code for code, item in open_ended.items() if item.domain == "waste"]:
            waste_year[0][code if code in waste_year[0] else WASTE_TOTAL].provenance[
                "source_reported_ytd_not_combined"
            ] = _number(open_ended.pop(code).value, code)
    unmatched = [source for source in sources if source.has_data()]
    sources = list(unmatched)
    # A cumulative year-to-date source that starts on 1 January and ends INSIDE a
    # month (for example outreach "till 17 Aug") cannot be a month window: it is
    # a baseline of the year's YTD view, never a month. Later genuine months
    # extend it; overlapping months do not. A YTD source that ends on a month
    # end keeps its existing handling below.
    baselines = [
        source
        for source in unmatched
        if source.granularity == "YTD"
        and source.coverage_start == date(year, 1, 1)
        and source.coverage_end.day != calendar.monthrange(year, source.coverage_end.month)[1]
    ]
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
                if waste_year is not None and value.domain == "waste":
                    continue  # the year's waste is resolved once, by _waste_year_aggregate
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
        _aggregate_ghg_completeness(entry, months, window)
        for code in DG_ACTIVITY_CODES:
            # A window that spans the methodology change says so instead of
            # presenting derived and source-reported litres as one kind.
            origins = {value.activity_origin for _, value in by_code.get(code, []) if value.activity_origin}
            if code in entry.values and origins:
                entry.values[code].activity_origin = origins.pop() if len(origins) == 1 else "MIXED"
        for baseline in [item for item in baselines if (item.coverage_start, item.coverage_end) != (start, end)]:
            _apply_ytd_baseline(entry, baseline, months)
            unmatched.remove(baseline)
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
                        calculation_status=value.calculation_status,
                        contributors=value.contributors,
                        missing_contributors=value.missing_contributors,
                    )
        _derive_ratios(db, entry)
        _add_open_ended(entry, open_ended)
        result.append(entry)
    elif open_ended or baselines:
        # No genuine month this year: the confirmed figure is the year's YTD view.
        last_day = max((item.coverage_end for item in baselines), default=date(year, 12, 31))
        entry = Entry(
            f"{year}-YTD", f"{year} YTD", year, None, "YTD", date(year, 1, 1), last_day,
            "historical_verified",
        )
        for baseline in baselines:
            _apply_ytd_baseline(entry, baseline, [])
            unmatched.remove(baseline)
        _derive_ratios(db, entry)
        _add_open_ended(entry, open_ended)
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
    if waste_year is not None:
        waste_values, waste_end, full_year = waste_year
        # The year's Full Year view when the waste reaches 31 December, else its YTD view.
        preferred = (f"{year}-FY", f"{year}-YTD") if full_year else (f"{year}-YTD", f"{year}-FY")
        target = next((item for key in preferred for item in result if item.key == key), None)
        if target is None:
            target = Entry(
                f"{year}-FY" if full_year else f"{year}-YTD",
                f"{year} Full Year" if full_year else f"{year} YTD",
                year,
                None,
                "ANNUAL" if full_year else "YTD",
                date(year, 1, 1),
                waste_end,
                next(iter(waste_values.values())).source_kind,
            )
            _derive_ratios(db, target)
            result.insert(0, target)
        target.values.update(waste_values)
    return result


def _apply_ytd_baseline(entry: Entry, baseline: Entry, months: list[Entry]) -> None:
    """Year-to-date value = a cumulative source baseline + the genuine months after it.

    The baseline covers 1 January to its stated end date as one figure; it is
    never split into months. A month contributes only when it STARTS after the
    baseline's coverage end and reports the value in the same unit. A month
    that overlaps the baseline's coverage (including the month the baseline
    ends in) is not added - its remainder is not assumed to be zero, it is just
    not combined - so nothing is counted twice. A lower-bound baseline keeps
    its AT_LEAST qualifier.
    """
    later = [month for month in months if month.coverage_start > baseline.coverage_end]
    overlapping = [month for month in months if month.coverage_start <= baseline.coverage_end]
    for code, value in baseline.values.items():
        if value.value is None or code in NON_ADDITIVE_METRICS:
            continue

        def reported(month: Entry, code: str = code) -> Value | None:
            item = month.values.get(code)
            return item if item is not None and item.value is not None else None

        extendable = code not in BASELINE_NOT_EXTENDED
        added = [
            (month.key, item)
            for month in later
            if (item := reported(month)) is not None and extendable and item.unit == value.unit
        ]
        not_combined = [
            month.key
            for month in later
            if (item := reported(month)) is not None and (not extendable or item.unit != value.unit)
        ]
        total = value.value + sum((item.value for _, item in added if item.value is not None), Decimal("0"))
        qualifiers = {value.qualifier, *(item.qualifier for _, item in added)}
        # The public label is simply "<year> YTD". The baseline's exact coverage
        # dates and the months added to it stay in the provenance below.
        label = f"{entry.year} YTD"
        entry.values[code] = Value(
            code,
            value.domain,
            value.kind,
            total,
            value.unit,
            qualifier=value.qualifier
            if value.qualifier == "AT_LEAST"
            else ("EXACT" if qualifiers == {"EXACT"} else "APPROXIMATE"),
            source_kind="historical_verified" if not added else "mixed_aggregate",
            granularity="YTD",
            coverage_status="complete",
            months_covered=[key for key, _ in added],
            provenance={
                **value.provenance,
                "aggregation": RUNNING_YTD,
                "baseline_value": _number(value.value, code),
                "baseline_coverage_start": baseline.coverage_start.isoformat(),
                "baseline_coverage_end": baseline.coverage_end.isoformat(),
                "months_added": [key for key, _ in added],
                "months_excluded_overlap": [month.key for month in overlapping if reported(month) is not None],
                "months_not_combined": not_combined,
            },
            coverage_label=label,
        )


def _aggregate_ghg_completeness(entry: Entry, months: list[Entry], window: list[str]) -> None:
    """Completeness of a Full Year / YTD GHG total summed from monthly values.

    COMPLETE only when every month of the window has a COMPLETE monthly value.
    Otherwise PARTIAL: each contributor states the months it covers and the
    months it lacks, and a contributor with no month at all is listed as
    missing. Months and contributors that are absent are not counted as zero.
    """
    by_key = {month.key: month for month in months}

    def month_status(month_key: str, code: str) -> str | None:
        value = by_key[month_key].values.get(code) if month_key in by_key else None
        return None if value is None or value.value is None else (value.calculation_status or COMPLETE)

    for code in (GRID_EMISSIONS, *GHG_TOTAL_CONTRIBUTORS):
        total = entry.values.get(code)
        if total is None or total.value is None:
            continue
        contributors: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for part in GHG_TOTAL_CONTRIBUTORS.get(code, ()):
            item = entry.values.get(part)
            named = {"code": part, "label": CONTRIBUTOR_LABELS.get(part, part)}
            if item is None or item.value is None:
                missing.append({**named, "months_missing": window})
                continue
            contributors.append(
                {
                    **named,
                    "value": _number(item.value, part),
                    "unit": item.unit,
                    "status": COMPLETE
                    if all(month_status(month_key, part) == COMPLETE for month_key in window)
                    else PARTIAL,
                    "months_covered": item.months_covered,
                    "months_missing": [key for key in window if key not in item.months_covered],
                }
            )
        total.calculation_status = (
            COMPLETE if all(month_status(month_key, code) == COMPLETE for month_key in window) else PARTIAL
        )
        total.contributors = contributors
        total.missing_contributors = missing


def _add_open_ended(entry: Entry, open_ended: dict[str, Value]) -> None:
    """Add confirmed open-ended YTD figures, never on top of monthly data.

    Their end month is unknown, so whether they overlap genuine monthly values
    cannot be established: a metric that has any monthly-derived value keeps
    only that value, and the source figure is recorded in its provenance.
    """
    for code, value in open_ended.items():
        existing = entry.values.get(code)
        if existing is not None and existing.value is not None:
            existing.provenance = {
                **existing.provenance,
                "source_reported_ytd_not_combined": _number(value.value, code),
            }
            continue
        entry.values[code] = replace(
            value,
            source_kind="historical_verified",
            granularity="YTD",
            coverage_status="complete",
            months_covered=[],
            provenance={**value.provenance, "aggregation": "source_reported_year_to_date"},
        )


STATIC_LABEL = "Institutional Reference"


def _is_running_outreach(aggregate: Entry) -> bool:
    """True when the year's outreach is a cumulative baseline plus later months."""
    return any(
        value.domain == "outreach" and value.value is not None and value.provenance.get("aggregation") == RUNNING_YTD
        for value in aggregate.values.values()
    )


def _show_running_outreach(period: dict[str, Any], running: Entry) -> None:
    """Every month of a running-YTD year SHOWS the year's current outreach YTD.

    Presentation only. Outreach in such a year is one year-to-date dataset, so
    selecting a month does not filter it: the month's outreach cards and charts
    resolve to the YTD aggregate, labelled "<year> YTD" and flagged as context.
    Nothing is written into the month's ``values`` - no monthly outreach figure
    is created, and a month's own genuine outreach values stay where they are.
    """
    display = period["display"]
    for code in [code for code, item in display.items() if item.get("domain") == "outreach"]:
        del display[code]
    for code, value in running.values.items():
        if value.domain == "outreach" and value.value is not None:
            label = value.coverage_label or f"{running.year} YTD"
            display[code] = _display_item(value, running, label, context=True)
    period["domains"]["outreach"] = {
        "state": "year_to_date",
        "alternative_key": running.key,
        "message": f"{running.year} outreach is reported as one year-to-date figure, not a monthly value.",
    }


def _waste_year_entry(aggregates: list[Entry]) -> Entry | None:
    return next(
        (
            item
            for item in aggregates
            if any(value.provenance.get("aggregation") == WASTE_YEAR_AGGREGATE for value in item.values.values())
        ),
        None,
    )


def _show_waste_year(period: dict[str, Any], waste: Entry) -> None:
    """Every selection inside a year SHOWS that year's current Waste aggregate.

    Presentation only. Waste is one running figure per year, so a month does
    not filter it: the month's waste cards and charts resolve to the year's
    aggregate, labelled "<year> Full Year" or "<year> YTD" and flagged as
    context. Nothing is written into the month's ``values`` - no monthly waste
    figure is created, and a published month keeps its own values there.
    """
    display = period["display"]
    for code in [
        code
        for code, item in display.items()
        if item.get("domain") == "waste" and item.get("source_granularity") != "STATIC"
    ]:
        del display[code]
    label = f"{waste.year} YTD"
    for code, value in waste.values.items():
        if value.domain == "waste" and value.value is not None:
            label = value.coverage_label or label
            display[code] = _display_item(value, waste, label, context=True)
    period["domains"]["waste"] = {
        "state": "year_aggregate",
        "alternative_key": waste.key,
        "label": label,
        "message": f"Waste is reported as one figure for the year ({label}); the selected month does not filter it.",
    }


def _aggregate_label(entry: Entry) -> str:
    if entry.granularity == "ANNUAL":
        return f"{entry.year} Annual Data"
    start, end = calendar.month_abbr[entry.coverage_start.month], calendar.month_abbr[entry.coverage_end.month]
    return f"{entry.year} YTD · {start}–{end}"


def _display_item(value: Value, entry: Entry, label: str, *, context: bool) -> dict[str, Any]:
    return {
        **value.completeness_json(),
        **value.origin_json(),
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


def _partial_label(entry: Entry, value: Value, window: int) -> str:
    """'Jan–May 2026' when a current-year KPI covers the window's first months, else 'N of W months'."""
    if value.code in CURRENT_YEAR_KPI_CODES and value.months_covered:
        first = entry.coverage_start
        expected = [_month_key(first.year, first.month + offset) for offset in range(len(value.months_covered))]
        if value.months_covered == expected:
            last = int(value.months_covered[-1][5:7])
            span = calendar.month_abbr[first.month]
            if last != first.month:
                span = f"{span}–{calendar.month_abbr[last]}"
            return f"{span} {entry.year}"
    return f"{entry.year} · {len(value.months_covered)} of {window} months"


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
    covering = [item for item in aggregates if item.coverage_start <= month_date <= item.coverage_end]
    annual_first = sorted(covering, key=lambda item: 0 if item.granularity == "ANNUAL" else 1)
    # Current-year KPIs: exact month, then year-to-date context, then annual context.
    ytd_first = sorted(covering, key=lambda item: 0 if item.granularity == "YTD" else 1)
    for prefer_ytd, candidates in ((True, ytd_first), (False, annual_first)):
        for aggregate in candidates:
            for code, value in aggregate.values.items():
                if (code in CURRENT_YEAR_KPI_CODES) != prefer_ytd:
                    continue
                if code in display or code == "population" or value.value is None:
                    continue
                if value.coverage_status != "complete" or value.calculation_status == PARTIAL:
                    continue  # a partial-period or partial-source sum is never context for a month
                label = value.coverage_label or _aggregate_label(aggregate)
                display[code] = _display_item(value, aggregate, label, context=True)
    return display


def _aggregate_display(entry: Entry, static: dict[str, Any]) -> dict[str, Any]:
    """A Full Year / YTD view shows its own values; partial sums say how many months they cover.

    A partial GHG total is shown too (available-data methodology): its display
    item carries ``calculation_status`` PARTIAL, its contributors and what is
    missing, so it is never mistaken for a complete inventory total.
    """
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
        if value.coverage_label:
            item_label = value.coverage_label
        elif value.coverage_status == "partial":
            item_label = _partial_label(entry, value, window)
        else:
            item_label = label
        display[code] = _display_item(value, entry, item_label, context=False)
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


# A month reported by a single operational domain (for example LPG alone) is not
# an institution-wide reporting month. It stays selectable and queryable, but
# it never becomes the default view.
DEFAULT_MIN_REPORTING_DOMAINS = 2


def _reporting_domains(entry: Entry) -> set[str]:
    return {value.domain for value in entry.values.values() if value.value is not None and value.domain in DOMAINS}


def _default_month(months: list[Entry]) -> Entry | None:
    def recency(item: Entry) -> tuple[int, int]:
        return (item.year, item.month or 0)

    institution_wide = [
        item for item in months if len(_reporting_domains(item)) >= DEFAULT_MIN_REPORTING_DOMAINS
    ]
    return max(institution_wide or months, key=recency, default=None)


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
            periods[aggregate.key]["display"] = _aggregate_display(aggregate, static)
            if aggregate.key == f"{year}-FY":
                label = "Full Year"
            elif aggregate.key == f"{year}-YTD":
                label = "YTD"  # each card states its own coverage
            else:
                label = aggregate.label.split(" ", 1)[1]
            options.append({"key": aggregate.key, "label": label, "granularity": aggregate.granularity})
        population, source = population_for(db, year)
        running_outreach = next((item for item in aggregates if _is_running_outreach(item)), None)
        waste_entry = _waste_year_entry(aggregates)
        if waste_entry is not None:
            for aggregate in aggregates:
                if aggregate is not waste_entry:
                    _show_waste_year(periods[aggregate.key], waste_entry)
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
            periods[entry.key]["display"] = _month_display(entry, aggregates, static)
            if running_outreach is not None:
                _show_running_outreach(periods[entry.key], running_outreach)
            if waste_entry is not None:
                _show_waste_year(periods[entry.key], waste_entry)
            options.append({"key": entry.key, "label": calendar.month_abbr[entry.month or 1], "granularity": "MONTHLY"})
        selector.append({"year": year, "options": options})
    latest = _default_month(list(monthly.values()))
    materials = {row.code: row.display_name for row in db.scalars(select(WasteMaterial)).all()}
    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "default_key": latest.key if latest else None,
        "selector": selector,
        "periods": periods,
        "labels": {
            **{f"material:{code}": name for code, name in sorted(materials.items())},
            WASTE_DIVERTED: "Waste Diverted from Landfill",
        },
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
