from calendar import month_name
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.enums import OperationalDomain, SubmissionStatus
from app.models.sustainability import MetricDefinition, Submission
from app.schemas.auth import MessageResponse
from app.schemas.outreach import CurrentPeriodResponse, PeriodResponse
from app.schemas.submissions import (
    GenericSubmissionResponse,
    MetricDefinitionResponse,
    SubmissionCreate,
    SubmissionUpdate,
)
from app.schemas.waste import WasteCatalogResponse
from app.security.dependencies import CsrfUser, DbSession, ManagerUser, enforce_manager_domain
from app.services import dg_methodology as dg
from app.services import waste as waste_service
from app.services.audit import add_audit_log
from app.services.emission_factors import freeze_calculations
from app.services.evidence import commit_temporary_evidence
from app.services.reporting_periods import (
    current_reporting_period,
    require_current_period_for_create,
    require_manager_mutation,
)
from app.services.submission_workflow import (
    GENERIC_DOMAINS,
    get_owned_submission,
    save_values,
    serialize_submission,
    submit,
)

router = APIRouter(prefix="/api/manager", tags=["manager submissions"])


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _require_domain(current: ManagerUser | CsrfUser, domain: OperationalDomain) -> None:
    if domain not in GENERIC_DOMAINS:
        raise HTTPException(status_code=404, detail="Generic submission workflow is not available for this domain.")
    enforce_manager_domain(current, domain)


def _require_current_version(submission: Submission, expected_row_version: int | None) -> None:
    if expected_row_version != submission.row_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stale_submission",
                "message": "This submission has changed. Refresh to load the latest version.",
                "current_row_version": submission.row_version,
            },
        )


@router.get("/{domain}/periods", response_model=list[PeriodResponse])
def list_periods(
    domain: OperationalDomain, request: Request, current: ManagerUser, db: DbSession
) -> list[PeriodResponse]:
    _require_domain(current, domain)
    item = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    return [
        PeriodResponse(
            id=item.id,
            year=item.year,
            month=item.month,
            label=f"{item.year}-{item.month:02d}",
            is_open=item.is_open,
        )
    ]


@router.get("/{domain}/current-period", response_model=CurrentPeriodResponse)
def get_current_period(
    domain: OperationalDomain, request: Request, current: ManagerUser, db: DbSession
) -> CurrentPeriodResponse:
    _require_domain(current, domain)
    item = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    return CurrentPeriodResponse(
        id=item.id,
        year=item.year,
        month=item.month,
        label=f"{month_name[item.month]} {item.year}",
        is_open=item.is_open,
    )


@router.get("/{domain}/metrics", response_model=list[MetricDefinitionResponse])
def list_metrics(
    domain: OperationalDomain, request: Request, current: ManagerUser, db: DbSession
) -> list[MetricDefinitionResponse]:
    _require_domain(current, domain)
    # Managers enter the current reporting month only, so the DG activity that
    # is not that month's source (litres once the governed SFC is in force) is
    # not offered as an input.
    hidden = None
    if domain is OperationalDomain.TRANSPORT:
        period = current_reporting_period(db, request.app.state.settings, request.app.state.institutional_clock)
        hidden = dg.superseded_manager_metric(db, period.period_start)
    metrics = db.scalars(
        select(MetricDefinition)
        .where(MetricDefinition.operational_domain == domain, MetricDefinition.is_active.is_(True))
        .order_by(MetricDefinition.display_order, MetricDefinition.code)
    ).all()
    return [
        MetricDefinitionResponse(
            code=item.code,
            display_name=item.display_name,
            canonical_unit=item.canonical_unit,
            required_for_complete=item.required_for_complete,
            zero_allowed=item.zero_allowed,
            manager_editable=item.manager_editable,
            display_order=item.display_order,
        )
        for item in metrics
        if item.code != hidden
    ]


@router.get("/waste/catalog", response_model=WasteCatalogResponse)
def waste_catalog(current: ManagerUser, db: DbSession) -> WasteCatalogResponse:
    """Controlled waste categories and materials for the Manager dropdowns.

    The catalog is never hardcoded in the browser: the page renders whatever
    this returns, and only active entries are returned.
    """
    enforce_manager_domain(current, OperationalDomain.WASTE)
    return waste_service.catalog(db)


@router.get("/{domain}/submissions/current", response_model=GenericSubmissionResponse | None)
def current_submission(
    domain: OperationalDomain,
    reporting_period_id: UUID,
    current: ManagerUser,
    db: DbSession,
) -> GenericSubmissionResponse | None:
    _require_domain(current, domain)
    submission = db.scalar(
        select(Submission).where(
            Submission.domain == domain,
            Submission.reporting_period_id == reporting_period_id,
            Submission.manager_user_id == current.user_id,
            Submission.status != SubmissionStatus.SUPERSEDED,
        )
    )
    return serialize_submission(db, submission) if submission else None


@router.get("/{domain}/submissions", response_model=list[GenericSubmissionResponse])
def submission_history(
    domain: OperationalDomain, current: ManagerUser, db: DbSession
) -> list[GenericSubmissionResponse]:
    _require_domain(current, domain)
    submissions = db.scalars(
        select(Submission)
        .where(Submission.domain == domain, Submission.manager_user_id == current.user_id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [serialize_submission(db, item) for item in submissions]


@router.get("/{domain}/submissions/{submission_id}", response_model=GenericSubmissionResponse)
def submission_detail(
    domain: OperationalDomain,
    submission_id: UUID,
    current: ManagerUser,
    db: DbSession,
) -> GenericSubmissionResponse:
    _require_domain(current, domain)
    return serialize_submission(db, get_owned_submission(db, submission_id, current.user_id, domain))


@router.post("/{domain}/submissions", response_model=GenericSubmissionResponse, status_code=201)
def create_or_save_draft(
    domain: OperationalDomain,
    payload: SubmissionCreate,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> GenericSubmissionResponse:
    _require_domain(current, domain)
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_current_period_for_create(payload.reporting_period_id, period)
    submission = db.scalar(
        select(Submission).where(
            Submission.domain == domain,
            Submission.reporting_period_id == period.id,
            Submission.status != SubmissionStatus.SUPERSEDED,
        ).with_for_update()
    )
    created = submission is None
    if submission is None:
        submission = Submission(
            domain=domain,
            manager_user_id=current.user_id,
            reporting_period_id=period.id,
            status=SubmissionStatus.DRAFT,
        )
        db.add(submission)
        try:
            db.flush()
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="An active submission already exists for this period.") from exc
    if submission.manager_user_id != current.user_id:
        raise HTTPException(status_code=409, detail="This reporting-period submission belongs to another manager.")
    if not created:
        _require_current_version(submission, payload.expected_row_version)
    require_manager_mutation(submission, period)
    save_values(db, submission, payload.values, payload.remarks, payload.waste_items)
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=f"{domain.value}.draft_{'created' if created else 'saved'}",
        target_type="submission",
        target_reference=str(submission.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission)


@router.put("/{domain}/submissions/{submission_id}", response_model=GenericSubmissionResponse)
def update_draft(
    domain: OperationalDomain,
    submission_id: UUID,
    payload: SubmissionUpdate,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> GenericSubmissionResponse:
    _require_domain(current, domain)
    submission = get_owned_submission(db, submission_id, current.user_id, domain, for_update=True)
    _require_current_version(submission, payload.expected_row_version)
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, period)
    save_values(db, submission, payload.values, payload.remarks, payload.waste_items)
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=f"{domain.value}.draft_updated",
        target_type="submission",
        target_reference=str(submission.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    db.refresh(submission)
    return serialize_submission(db, submission)


@router.post("/{domain}/submissions/{submission_id}/submit", response_model=MessageResponse)
def submit_for_review(
    domain: OperationalDomain,
    submission_id: UUID,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    _require_domain(current, domain)
    submission = get_owned_submission(db, submission_id, current.user_id, domain, for_update=True)
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, period)
    submit(db, submission, current.user_id)
    freeze_calculations(db, submission)
    committed_evidence = commit_temporary_evidence(db, submission)
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=f"{domain.value}.submitted",
        target_type="submission",
        target_reference=str(submission.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"revision_number": submission.revision_number},
    )
    if committed_evidence:
        add_audit_log(
            db,
            actor_user_id=current.user_id,
            actor_type="user",
            event_type="evidence.committed",
            target_type="submission",
            target_reference=str(submission.id),
            outcome="succeeded",
            request_id=_request_id(request),
            metadata={
                "submission_id": str(submission.id),
                "domain": domain.value,
                "revision_number": submission.revision_number,
                "evidence_ids": [str(item.id) for item in committed_evidence],
            },
        )
    db.commit()
    return MessageResponse(message=f"{domain.value.title()} submission sent for review.")
