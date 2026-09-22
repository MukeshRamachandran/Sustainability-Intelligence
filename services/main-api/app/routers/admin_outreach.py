from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.models.enums import OperationalDomain, ReviewActionType, SubmissionStatus
from app.models.identity import User
from app.models.sustainability import OutreachProgramme, ReportingPeriod, ReviewAction, Submission
from app.schemas.auth import MessageResponse
from app.schemas.outreach import CorrectionRequest, OutreachProgrammeResponse, OutreachSubmissionSummary, PeriodResponse
from app.schemas.submissions import GenericSubmissionResponse
from app.security.dependencies import AdminUser, CsrfUser, DbSession, require_admin
from app.services.audit import add_audit_log
from app.services.outreach import correction_reason
from app.services.outreach import submission_snapshot as outreach_submission_snapshot
from app.services.submission_workflow import (
    get_submission as get_generic_submission,
)
from app.services.submission_workflow import (
    serialize_submission,
)
from app.services.submission_workflow import (
    submission_snapshot as generic_submission_snapshot,
)

router = APIRouter(prefix="/api/admin", tags=["admin outreach"])


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _admin(current: CsrfUser) -> None:
    require_admin(current)


def _submission(db: DbSession, submission_id: UUID, *, for_update: bool = False) -> Submission:
    query = select(Submission).where(Submission.id == submission_id)
    submission = db.scalar(query.with_for_update() if for_update else query)
    if submission is None:
        raise HTTPException(status_code=404, detail="Outreach submission not found.")
    return submission


def _snapshot(db: DbSession, submission: Submission) -> dict[str, object]:
    if submission.domain == OperationalDomain.OUTREACH:
        return outreach_submission_snapshot(db, submission)
    return generic_submission_snapshot(db, get_generic_submission(db, submission.id))


def _programme_response(
    db: DbSession, programme: OutreachProgramme, submission: Submission, period: ReportingPeriod
) -> OutreachProgrammeResponse:
    return OutreachProgrammeResponse(
        **{column.name: getattr(programme, column.name) for column in OutreachProgramme.__table__.columns},
        reporting_period_id=period.id,
        reporting_period_label=f"{period.year}-{period.month:02d}",
        status=submission.status,
        revision_number=submission.revision_number,
        row_version=submission.row_version,
        submitted_at=submission.submitted_at,
        correction_reason=correction_reason(db, submission.id),
    )


def _summary(db: DbSession, submission: Submission) -> OutreachSubmissionSummary:
    period = db.get(ReportingPeriod, submission.reporting_period_id)
    manager = db.get(User, submission.manager_user_id)
    if period is None:
        raise HTTPException(status_code=500, detail="Submission reporting period is missing.")
    programmes = db.scalars(
        select(OutreachProgramme)
        .where(OutreachProgramme.submission_id == submission.id)
        .order_by(OutreachProgramme.programme_date, OutreachProgramme.created_at)
    ).all()
    return OutreachSubmissionSummary(
        id=submission.id,
        domain=submission.domain,
        reporting_period_id=period.id,
        reporting_period_label=f"{period.year}-{period.month:02d}",
        status=submission.status,
        revision_number=submission.revision_number,
        row_version=submission.row_version,
        manager_display_name=manager.display_name if manager else None,
        submitted_at=submission.submitted_at,
        approved_at=submission.approved_at,
        correction_reason=correction_reason(db, submission.id),
        programme_count=len(programmes),
        programmes=[_programme_response(db, item, submission, period) for item in programmes],
    )


def _any_summary(db: DbSession, submission: Submission) -> OutreachSubmissionSummary | GenericSubmissionResponse:
    if submission.domain == OperationalDomain.OUTREACH:
        return _summary(db, submission)
    return serialize_submission(db, get_generic_submission(db, submission.id))


@router.get("/periods", response_model=list[PeriodResponse])
def admin_periods(current: AdminUser, db: DbSession) -> list[PeriodResponse]:
    periods = db.scalars(
        select(ReportingPeriod).order_by(ReportingPeriod.year.desc(), ReportingPeriod.month.desc())
    ).all()
    return [
        PeriodResponse(
            id=item.id, year=item.year, month=item.month, label=f"{item.year}-{item.month:02d}", is_open=item.is_open
        )
        for item in periods
    ]


@router.get("/review-queue", response_model=list[OutreachSubmissionSummary | GenericSubmissionResponse])
def review_queue(
    current: AdminUser,
    db: DbSession,
    domain: OperationalDomain | None = None,
    reporting_period_id: UUID | None = None,
) -> list[OutreachSubmissionSummary | GenericSubmissionResponse]:
    selected_domain = domain or OperationalDomain.OUTREACH
    statement = select(Submission).where(
        Submission.domain == selected_domain,
        Submission.status.in_([SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW]),
    )
    if reporting_period_id is not None:
        statement = statement.where(Submission.reporting_period_id == reporting_period_id)
    submissions = db.scalars(statement.order_by(Submission.submitted_at.asc())).all()
    return [_any_summary(db, item) for item in submissions]


@router.get("/submissions/{submission_id}", response_model=OutreachSubmissionSummary | GenericSubmissionResponse)
def submission_detail(
    submission_id: UUID, current: AdminUser, db: DbSession
) -> OutreachSubmissionSummary | GenericSubmissionResponse:
    return _any_summary(db, _submission(db, submission_id))


@router.post("/submissions/{submission_id}/begin-review", response_model=MessageResponse)
def begin_review(submission_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> MessageResponse:
    _admin(current)
    submission = _submission(db, submission_id, for_update=True)
    if submission.status != SubmissionStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="Only submitted records can begin review.")
    submission.status = SubmissionStatus.UNDER_REVIEW
    submission.row_version += 1
    db.add(
        ReviewAction(
            submission_id=submission.id,
            actor_user_id=current.user_id,
            action=ReviewActionType.BEGIN_REVIEW,
            from_status=SubmissionStatus.SUBMITTED,
            to_status=SubmissionStatus.UNDER_REVIEW,
        )
    )
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=f"{submission.domain.value}.review_started",
        target_type="submission",
        target_reference=str(submission.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return MessageResponse(message="Submission is under review.")


@router.post("/submissions/{submission_id}/request-correction", response_model=MessageResponse)
def request_correction(
    submission_id: UUID,
    payload: CorrectionRequest,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    _admin(current)
    submission = _submission(db, submission_id, for_update=True)
    if submission.status not in {SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW}:
        raise HTTPException(status_code=409, detail="Submission cannot be returned for correction.")
    previous = submission.status
    submission.status = SubmissionStatus.CORRECTION_REQUESTED
    submission.row_version += 1
    db.add(
        ReviewAction(
            submission_id=submission.id,
            actor_user_id=current.user_id,
            action=ReviewActionType.REQUEST_CORRECTION,
            from_status=previous,
            to_status=SubmissionStatus.CORRECTION_REQUESTED,
            comment=payload.reason,
            snapshot=_snapshot(db, submission),
        )
    )
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=f"{submission.domain.value}.correction_requested",
        target_type="submission",
        target_reference=str(submission.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return MessageResponse(message="Correction requested.")


@router.post("/submissions/{submission_id}/approve", response_model=MessageResponse)
def approve_submission(submission_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> MessageResponse:
    _admin(current)
    submission = _submission(db, submission_id, for_update=True)
    if submission.status not in {SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW}:
        raise HTTPException(status_code=409, detail="Submission cannot be approved.")
    previous = submission.status
    now = datetime.now(UTC)
    submission.status = SubmissionStatus.APPROVED
    submission.approved_at = now
    submission.approved_by = current.user_id
    submission.row_version += 1
    db.add(
        ReviewAction(
            submission_id=submission.id,
            actor_user_id=current.user_id,
            action=ReviewActionType.APPROVE,
            from_status=previous,
            to_status=SubmissionStatus.APPROVED,
            snapshot=_snapshot(db, submission),
        )
    )
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=f"{submission.domain.value}.approved",
        target_type="submission",
        target_reference=str(submission.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    label = "Outreach" if submission.domain == OperationalDomain.OUTREACH else submission.domain.value.title()
    return MessageResponse(message=f"{label} submission approved. Publication is still required.")
