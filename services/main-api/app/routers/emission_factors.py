from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.models.enums import FactorSetStatus
from app.models.sustainability import EmissionFactor, EmissionFactorSet
from app.schemas.emission_factors import FactorSetCreate, FactorSetResponse, FactorSetUpdate
from app.security.dependencies import AdminUser, CsrfUser, DbSession, require_admin
from app.services.audit import add_audit_log
from app.services.emission_factors import (
    flush_governance,
    replace_factors,
    serialize_factor_set,
    validate_activation,
)

router = APIRouter(prefix="/api/admin/emission-factor-sets", tags=["emission factor governance"])


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _locked(db: DbSession, set_id: UUID) -> EmissionFactorSet:
    item = db.scalar(select(EmissionFactorSet).where(EmissionFactorSet.id == set_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Emission factor set not found.")
    return item


@router.get("", response_model=list[FactorSetResponse])
def list_factor_sets(current: AdminUser, db: DbSession) -> list[FactorSetResponse]:
    items = db.scalars(
        select(EmissionFactorSet).order_by(
            EmissionFactorSet.effective_from.desc().nullslast(), EmissionFactorSet.created_at.desc()
        )
    ).all()
    return [serialize_factor_set(db, item) for item in items]


@router.get("/{set_id}", response_model=FactorSetResponse)
def get_factor_set(set_id: UUID, current: AdminUser, db: DbSession) -> FactorSetResponse:
    item = db.get(EmissionFactorSet, set_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Emission factor set not found.")
    return serialize_factor_set(db, item)


@router.post("", response_model=FactorSetResponse, status_code=status.HTTP_201_CREATED)
def create_factor_set(
    payload: FactorSetCreate, request: Request, current: CsrfUser, db: DbSession
) -> FactorSetResponse:
    require_admin(current)
    item = EmissionFactorSet(
        version=payload.version,
        status=FactorSetStatus.DRAFT,
        effective_from=payload.effective_from,
        source_note=payload.source_note,
        created_by=current.user_id,
    )
    db.add(item)
    flush_governance(db)
    replace_factors(db, item, payload)
    flush_governance(db)
    add_audit_log(
        db, actor_user_id=current.user_id, actor_type="user",
        event_type="emission_factor_set.created", target_type="emission_factor_set",
        target_reference=str(item.id), outcome="succeeded", request_id=_request_id(request),
        metadata={"version": item.version, "effective_from": payload.effective_from.isoformat(),
                  "factor_codes": [factor.code.value for factor in payload.factors]},
    )
    db.commit()
    db.refresh(item)
    return serialize_factor_set(db, item)


@router.put("/{set_id}", response_model=FactorSetResponse)
def update_factor_set(
    set_id: UUID, payload: FactorSetUpdate, request: Request, current: CsrfUser, db: DbSession
) -> FactorSetResponse:
    require_admin(current)
    item = _locked(db, set_id)
    if item.status != FactorSetStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Active factor sets are immutable.")
    if item.row_version != payload.expected_row_version:
        raise HTTPException(
            status_code=409,
            detail={"code": "stale_factor_set", "message": "Factor set changed. Refresh and retry."},
        )
    item.version = payload.version
    item.effective_from = payload.effective_from
    item.source_note = payload.source_note
    item.row_version += 1
    item.updated_at = datetime.now(UTC)
    replace_factors(db, item, payload)
    flush_governance(db)
    add_audit_log(
        db, actor_user_id=current.user_id, actor_type="user",
        event_type="emission_factor_set.updated", target_type="emission_factor_set",
        target_reference=str(item.id), outcome="succeeded", request_id=_request_id(request),
        metadata={"version": item.version, "effective_from": payload.effective_from.isoformat(),
                  "factor_codes": [factor.code.value for factor in payload.factors]},
    )
    db.commit()
    db.refresh(item)
    return serialize_factor_set(db, item)


@router.post("/{set_id}/activate", response_model=FactorSetResponse)
def activate_factor_set(
    set_id: UUID, request: Request, current: CsrfUser, db: DbSession
) -> FactorSetResponse:
    require_admin(current)
    item = _locked(db, set_id)
    if item.status != FactorSetStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft factor sets can be activated.")
    validate_activation(db, item)
    item.status = FactorSetStatus.ACTIVE
    item.activated_at = datetime.now(UTC)
    item.activated_by = current.user_id
    item.row_version += 1
    item.updated_at = item.activated_at
    add_audit_log(
        db, actor_user_id=current.user_id, actor_type="user",
        event_type="emission_factor_set.activated", target_type="emission_factor_set",
        target_reference=str(item.id), outcome="succeeded", request_id=_request_id(request),
        metadata={
            "version": item.version,
            "effective_from": item.effective_from.isoformat() if item.effective_from else None,
            "factor_codes": [
                factor.code
                for factor in db.scalars(
                    select(EmissionFactor).where(EmissionFactor.factor_set_id == item.id)
                ).all()
            ],
        },
    )
    flush_governance(db)
    db.commit()
    db.refresh(item)
    return serialize_factor_set(db, item)
