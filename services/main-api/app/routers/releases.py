from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update

from app.historical.resolver import build_timeline, is_publicly_visible, visible_official_releases
from app.models.enums import ReleaseStatus
from app.models.publication import PublicRelease, PublicReleasePayload
from app.models.sustainability import ReportingPeriod
from app.schemas.auth import MessageResponse
from app.schemas.outreach import ReleasePrepareRequest, ReleaseResponse, ReleaseSummary
from app.schemas.publication import PublicationReadinessResponse
from app.security.dependencies import AdminUser, CsrfUser, DbSession, require_admin
from app.services.audit import add_audit_log
from app.services.publication import (
    build_release_payload,
    derived_payload_blockers,
    empty_public_dashboard,
    lpg_payload_blockers,
    payload_checksum,
    waste_payload_blockers,
)
from app.services.publication_readiness import (
    REQUIRED_PUBLICATION_DOMAINS,
    evaluate_publication_readiness,
    frozen_payload_blockers,
)

admin_router = APIRouter(prefix="/api/admin/releases", tags=["releases"])
readiness_router = APIRouter(prefix="/api/admin", tags=["publication readiness"])
public_router = APIRouter(prefix="/api/public", tags=["public"])


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _response(release: PublicRelease, payload: PublicReleasePayload) -> ReleaseResponse:
    return ReleaseResponse(
        id=release.id,
        version=release.version,
        status=release.status.value,
        checksum_sha256=release.checksum_sha256,
        reporting_period_id=release.reporting_period_id,
        payload=payload.payload,
    )


def _public_response(release: PublicRelease, payload: PublicReleasePayload) -> dict[str, object]:
    return {
        "release": {
            "version": release.version,
            "published_at": release.published_at.isoformat() if release.published_at else None,
            "checksum_sha256": release.checksum_sha256,
        },
        **payload.payload,
    }


def _not_ready_detail(readiness: PublicationReadinessResponse) -> dict[str, object]:
    return {
        "code": "publication_not_ready",
        "message": "All required domains must be approved before publication preparation.",
        "approved_domains": readiness.approved_domains,
        "required_domains": readiness.required_domains,
        "blockers": [item.model_dump(mode="json") for item in readiness.blockers],
    }


@readiness_router.get(
    "/reporting-periods/{reporting_period_id}/publication-readiness",
    response_model=PublicationReadinessResponse,
)
def publication_readiness(
    reporting_period_id: UUID,
    current: AdminUser,
    db: DbSession,
) -> PublicationReadinessResponse:
    period = db.get(ReportingPeriod, reporting_period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Reporting period not found.")
    return evaluate_publication_readiness(db, period)


@admin_router.post("/prepare", response_model=ReleaseResponse, status_code=201)
def prepare_release(
    body: ReleasePrepareRequest,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> ReleaseResponse:
    require_admin(current)
    period = db.get(ReportingPeriod, body.reporting_period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Reporting period not found.")
    readiness = evaluate_publication_readiness(db, period)
    if not readiness.ready_to_publish:
        raise HTTPException(status_code=409, detail=_not_ready_detail(readiness))
    if db.scalar(select(PublicRelease.id).where(PublicRelease.version == body.version)):
        raise HTTPException(status_code=409, detail="Release version already exists.")
    payload_data = build_release_payload(db, period)
    frozen_blockers = (
        frozen_payload_blockers(payload_data)
        + waste_payload_blockers(payload_data)
        + derived_payload_blockers(payload_data)
        + lpg_payload_blockers(payload_data)
    )
    if frozen_blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "publication_not_ready",
                "message": "All required domains must be approved before publication preparation.",
                "approved_domains": readiness.approved_domains,
                "required_domains": readiness.required_domains,
                "blockers": frozen_blockers,
            },
        )
    release = PublicRelease(
        version=body.version,
        status=ReleaseStatus.CANDIDATE,
        checksum_sha256=payload_checksum(payload_data),
        prepared_by=current.user_id,
        reporting_period_id=period.id,
    )
    db.add(release)
    db.flush()
    payload = PublicReleasePayload(release_id=release.id, payload=payload_data)
    db.add(payload)
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="release.prepared",
        target_type="public_release",
        target_reference=str(release.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={
            "version": body.version,
            "checksum": release.checksum_sha256,
            "approved_domains": readiness.approved_domains,
            "required_domains": readiness.required_domains,
        },
    )
    db.commit()
    return _response(release, payload)


@admin_router.get("", response_model=list[ReleaseSummary])
def list_releases(reporting_period_id: UUID, current: AdminUser, db: DbSession) -> list[ReleaseSummary]:
    # Lets the Admin page rediscover an already-prepared candidate from the
    # database after a reload, instead of relying on in-page memory.
    if db.get(ReportingPeriod, reporting_period_id) is None:
        raise HTTPException(status_code=404, detail="Reporting period not found.")
    releases = db.scalars(
        select(PublicRelease)
        .where(PublicRelease.reporting_period_id == reporting_period_id)
        .order_by(PublicRelease.created_at.desc(), PublicRelease.id.desc())
    ).all()
    return [
        ReleaseSummary(
            id=release.id,
            version=release.version,
            status=release.status.value,
            checksum_sha256=release.checksum_sha256,
            reporting_period_id=release.reporting_period_id,
            created_at=release.created_at,
            published_at=release.published_at,
        )
        for release in releases
    ]


@admin_router.get("/{release_id}/preview", response_model=ReleaseResponse)
def preview_release(release_id: UUID, current: AdminUser, db: DbSession) -> ReleaseResponse:
    row = db.execute(
        select(PublicRelease, PublicReleasePayload)
        .join(PublicReleasePayload, PublicReleasePayload.release_id == PublicRelease.id)
        .where(PublicRelease.id == release_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Release not found.")
    return _response(*row)


@admin_router.post("/{release_id}/publish", response_model=MessageResponse)
def publish_release(release_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> MessageResponse:
    require_admin(current)
    release = db.scalar(select(PublicRelease).where(PublicRelease.id == release_id).with_for_update())
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found.")
    if release.status != ReleaseStatus.CANDIDATE:
        raise HTTPException(status_code=409, detail="Only candidate releases can be published.")
    payload = db.get(PublicReleasePayload, release.id)
    if payload is None or payload_checksum(payload.payload) != release.checksum_sha256:
        raise HTTPException(status_code=409, detail="Release payload checksum validation failed.")
    # Re-checked at publish so a candidate prepared before waste became
    # required cannot be published as if it were a complete six-domain release.
    frozen_blockers = (
        frozen_payload_blockers(payload.payload)
        + waste_payload_blockers(payload.payload)
        + derived_payload_blockers(payload.payload)
        + lpg_payload_blockers(payload.payload)
    )
    if frozen_blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "publication_not_ready",
                "message": "This frozen release candidate does not contain all required approved domains.",
                "approved_domains": len(REQUIRED_PUBLICATION_DOMAINS) - len(frozen_blockers),
                "required_domains": len(REQUIRED_PUBLICATION_DOMAINS),
                "blockers": frozen_blockers,
            },
        )
    now = datetime.now(UTC)
    db.execute(
        update(PublicRelease)
        .where(PublicRelease.status == ReleaseStatus.ACTIVE)
        .values(status=ReleaseStatus.SUPERSEDED)
    )
    release.status = ReleaseStatus.ACTIVE
    release.published_by = current.user_id
    release.published_at = now
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="release.published",
        target_type="public_release",
        target_reference=str(release.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"version": release.version, "checksum": release.checksum_sha256},
    )
    db.commit()
    return MessageResponse(message="Release published.")


@public_router.get("/dashboard")
def public_dashboard(db: DbSession, year: int | None = None, month: int | None = None) -> dict[str, object]:
    row = db.execute(
        select(PublicRelease, PublicReleasePayload)
        .join(PublicReleasePayload, PublicReleasePayload.release_id == PublicRelease.id)
        .where(PublicRelease.status == ReleaseStatus.ACTIVE)
    ).one_or_none()
    # A TEST / non-public release stays intact for audit but is never served publicly.
    if row is None or not is_publicly_visible(db, row[0].id):
        return empty_public_dashboard(year=year, month=month)
    release, payload = row
    period_data = payload.payload.get("period")
    if isinstance(period_data, dict) and (
        (year is not None and period_data.get("year") != year)
        or (month is not None and period_data.get("month") != month)
    ):
        return empty_public_dashboard(year=year, month=month)
    return _public_response(release, payload)


@public_router.get("/dashboard/timeline")
def public_dashboard_timeline(db: DbSession) -> dict[str, object]:
    """Official published releases merged with verified historical data."""
    return build_timeline(db)


@public_router.get("/dashboard/history")
def public_dashboard_history(db: DbSession) -> list[dict[str, object]]:
    rows = visible_official_releases(db)
    latest_by_period: dict[str, tuple[PublicRelease, PublicReleasePayload]] = {}
    for release, payload in rows:
        period = payload.payload.get("period")
        if not isinstance(period, dict):
            continue
        period_key = str(period.get("id") or f"{period.get('year')}-{period.get('month')}")
        latest_by_period.setdefault(period_key, (release, payload))

    def period_order(item: tuple[PublicRelease, PublicReleasePayload]) -> tuple[int, int, str]:
        release, payload = item
        period = payload.payload.get("period")
        if not isinstance(period, dict):
            return (0, 0, release.version)
        return (int(period.get("year") or 0), int(period.get("month") or 0), release.version)

    return [
        _public_response(release, payload)
        for release, payload in sorted(latest_by_period.values(), key=period_order)
    ]
