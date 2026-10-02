"""Governed Waste inventory service.

Waste is an activity/inventory domain: it has no emission factor and no GHG
methodology. The Manager supplies wet waste and a dry-material inventory; the
backend is the sole authority for the dry and total quantities.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain
from app.models.sustainability import (
    InstitutionalPopulationReference,
    ReportingPeriod,
    Submission,
    SubmissionValue,
    WasteCategory,
    WasteMaterial,
    WasteSubmissionItem,
)
from app.schemas.waste import (
    WasteCatalogCategory,
    WasteCatalogMaterial,
    WasteCatalogResponse,
    WasteItemResponse,
    WasteItemWrite,
    WasteSummaryResponse,
)
from app.services import sustainability_formulas as formulas

WET_METRIC = "wet_waste_generated_kg"
DRY_METRIC = "dry_waste_generated_kg"
TOTAL_METRIC = "total_waste_generated_kg"
DERIVED_METRICS = (DRY_METRIC, TOTAL_METRIC)
QUANTUM = Decimal("0.000001")


def catalog(db: Session, *, active_only: bool = True) -> WasteCatalogResponse:
    category_query = select(WasteCategory).order_by(WasteCategory.sort_order, WasteCategory.code)
    material_query = select(WasteMaterial).order_by(WasteMaterial.sort_order, WasteMaterial.code)
    if active_only:
        category_query = category_query.where(WasteCategory.is_active.is_(True))
        material_query = material_query.where(WasteMaterial.is_active.is_(True))
    categories = list(db.scalars(category_query).all())
    materials = list(db.scalars(material_query).all())
    active_category_codes = {item.code for item in categories}
    return WasteCatalogResponse(
        categories=[
            WasteCatalogCategory(
                code=item.code, display_name=item.display_name, sort_order=item.sort_order
            )
            for item in categories
        ],
        materials=[
            WasteCatalogMaterial(
                code=item.code,
                display_name=item.display_name,
                category_code=item.category_code,
                sort_order=item.sort_order,
            )
            for item in materials
            # A material whose category was retired must not surface orphaned.
            if item.category_code in active_category_codes
        ],
    )


def _active_materials(db: Session) -> dict[str, WasteMaterial]:
    return {
        item.code: item
        for item in db.scalars(
            select(WasteMaterial)
            .join(WasteCategory, WasteCategory.code == WasteMaterial.category_code)
            .where(WasteMaterial.is_active.is_(True), WasteCategory.is_active.is_(True))
        ).all()
    }


def validate_items(db: Session, items: list[WasteItemWrite]) -> list[tuple[WasteMaterial, Decimal]]:
    """Validate material codes and quantities. Duplicates are rejected here and
    again by uq_waste_item_submission_material, so a race cannot slip through."""
    seen: set[str] = set()
    known = _active_materials(db)
    validated: list[tuple[WasteMaterial, Decimal]] = []
    for item in items:
        material = known.get(item.material_code)
        if material is None:
            raise HTTPException(
                status_code=422,
                detail=f"Waste material '{item.material_code}' is not a valid active material.",
            )
        if item.material_code in seen:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "duplicate_waste_material",
                    "message": f"{material.display_name} has already been added. "
                    "Edit the existing quantity instead.",
                    "material_code": item.material_code,
                },
            )
        seen.add(item.material_code)
        validated.append((material, item.quantity_kg))
    return validated


def replace_items(db: Session, submission: Submission, items: list[WasteItemWrite]) -> None:
    """Replace the dry-waste inventory for this submission in the caller's
    transaction, so wet value, remarks and items move together or not at all."""
    validated = validate_items(db, items)
    db.execute(
        delete(WasteSubmissionItem).where(WasteSubmissionItem.submission_id == submission.id)
    )
    db.flush()
    for material, quantity in validated:
        db.add(
            WasteSubmissionItem(
                submission_id=submission.id,
                material_code=material.code,
                quantity_kg=quantity,
            )
        )
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "duplicate_waste_material",
                "message": "Each waste material may appear only once in a submission.",
            },
        ) from exc


def dry_total(db: Session, submission_id: object) -> Decimal:
    rows = db.scalars(
        select(WasteSubmissionItem.quantity_kg).where(
            WasteSubmissionItem.submission_id == submission_id
        )
    ).all()
    return sum(rows, Decimal("0")).quantize(QUANTUM)


def _wet_value(db: Session, submission_id: object) -> Decimal:
    value = db.scalar(
        select(SubmissionValue.value).where(
            SubmissionValue.submission_id == submission_id,
            SubmissionValue.metric_code == WET_METRIC,
        )
    )
    return (value if value is not None else Decimal("0")).quantize(QUANTUM)


def derived_values(db: Session, submission_id: object) -> dict[str, Decimal]:
    rows = db.execute(
        select(SubmissionValue.metric_code, SubmissionValue.value).where(
            SubmissionValue.submission_id == submission_id,
            SubmissionValue.metric_code.in_(DERIVED_METRICS),
        )
    ).all()
    return {code: (value if value is not None else Decimal("0")) for code, value in rows}


def items_response(db: Session, submission_id: object) -> list[WasteItemResponse]:
    rows = db.execute(
        select(WasteSubmissionItem, WasteMaterial, WasteCategory)
        .join(WasteMaterial, WasteMaterial.code == WasteSubmissionItem.material_code)
        .join(WasteCategory, WasteCategory.code == WasteMaterial.category_code)
        .where(WasteSubmissionItem.submission_id == submission_id)
        .order_by(WasteCategory.sort_order, WasteMaterial.sort_order, WasteMaterial.code)
    ).all()
    return [
        WasteItemResponse(
            material_code=item.material_code,
            material_display_name=material.display_name,
            category_code=category.code,
            category_display_name=category.display_name,
            quantity_kg=item.quantity_kg,
        )
        for item, material, category in rows
    ]


def summary(db: Session, submission: Submission) -> WasteSummaryResponse:
    """Read-back of the governed waste state. Dry and total come from the
    database-maintained derived metrics, never from client input."""
    items = items_response(db, submission.id)
    derived = derived_values(db, submission.id)
    dry = derived.get(DRY_METRIC, dry_total(db, submission.id))
    wet = _wet_value(db, submission.id)
    total = derived.get(TOTAL_METRIC, (wet + dry))
    by_category: dict[str, dict[str, object]] = {}
    for item in items:
        bucket = by_category.setdefault(
            item.category_code,
            {"code": item.category_code, "display_name": item.category_display_name,
             "quantity_kg": Decimal("0")},
        )
        bucket["quantity_kg"] = bucket["quantity_kg"] + item.quantity_kg  # type: ignore[operator]
    period = db.get(ReportingPeriod, submission.reporting_period_id)
    reference = db.get(InstitutionalPopulationReference, period.year) if period is not None else None
    per_person = formulas.waste_per_capita_kg(total, reference.population if reference is not None else None)
    diverted = formulas.waste_diverted_from_landfill_kg(dry)
    return WasteSummaryResponse(
        wet_waste_generated_kg=wet,
        dry_waste_generated_kg=dry,
        total_waste_generated_kg=total.quantize(QUANTUM),
        waste_diverted_from_landfill_kg=(diverted if diverted is not None else Decimal("0")).quantize(QUANTUM),
        waste_per_capita_kg=None if per_person is None else per_person.quantize(QUANTUM),
        items=items,
        categories=[
            WasteCatalogCategory(
                code=str(bucket["code"]),
                display_name=str(bucket["display_name"]),
                quantity_kg=Decimal(str(bucket["quantity_kg"])),
            )
            for bucket in by_category.values()
        ],
    )


def validate_waste_complete(db: Session, submission: Submission) -> None:
    """Submit-time guard. Wet waste presence is enforced by the generic
    required-metric check; this adds the waste-specific consistency rules."""
    if submission.domain is not OperationalDomain.WASTE:
        return
    items = db.scalars(
        select(WasteSubmissionItem).where(WasteSubmissionItem.submission_id == submission.id)
    ).all()
    known = _active_materials(db)
    for item in items:
        if item.material_code not in known:
            raise HTTPException(
                status_code=422,
                detail=f"Waste material '{item.material_code}' is no longer active.",
            )
        if not item.quantity_kg.is_finite() or item.quantity_kg <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"Waste material '{item.material_code}' must have a positive quantity.",
            )
    # An empty inventory is legitimate: dry waste is then zero, and no fake
    # material row is required.
    #
    # The derived metrics are maintained by trigger on every wet-value and item
    # change, so they are already current here. Verify rather than recompute:
    # a mismatch means something wrote around the triggers and must not be
    # carried into a submission.
    derived = derived_values(db, submission.id)
    expected_dry = dry_total(db, submission.id)
    stored_dry = derived.get(DRY_METRIC)
    stored_total = derived.get(TOTAL_METRIC)
    wet = _wet_value(db, submission.id)
    if stored_dry is None or stored_total is None:
        raise HTTPException(
            status_code=422,
            detail="Waste totals have not been calculated. Save the draft again.",
        )
    if stored_dry != expected_dry or stored_total != (wet + stored_dry):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "waste_totals_inconsistent",
                "message": "Waste totals do not match the recorded inventory. "
                "Save the draft again before submitting.",
            },
        )
