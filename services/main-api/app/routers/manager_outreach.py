from calendar import month_name
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.enums import OperationalDomain, ReviewActionType, SubmissionStatus
from app.models.sustainability import OutreachProgramme, ReportingPeriod, ReviewAction, Submission
from app.schemas.auth import MessageResponse
from app.schemas.outreach import (
    CurrentPeriodResponse,
    OutreachProgrammeCreate,
    OutreachProgrammeResponse,
    OutreachProgrammeUpdate,
    OutreachSubmissionSummary,
    PeriodResponse,
)
from app.security.dependencies import CsrfUser, DbSession, ManagerUser, enforce_manager_domain
from app.services.audit import add_audit_log
from app.services.evidence import commit_temporary_evidence
from app.services.outreach import correction_reason, submission_snapshot
from app.services.reporting_periods import (
    current_reporting_period,
    require_current_period_for_create,
    require_manager_mutation,
)

router = APIRouter(prefix="/api/manager", tags=["manager outreach"])


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _require_outreach(current: ManagerUser | CsrfUser) -> None:
    enforce_manager_domain(current, OperationalDomain.OUTREACH)


def _owned_programme(
    db: DbSession, user_id: UUID, programme_id: UUID, *, for_update: bool = False
) -> tuple[OutreachProgramme, Submission, ReportingPeriod]:
    query = (
        select(OutreachProgramme, Submission, ReportingPeriod)
        .join(Submission, Submission.id == OutreachProgramme.submission_id)
        .join(ReportingPeriod, ReportingPeriod.id == Submission.reporting_period_id)
        .where(
            OutreachProgramme.id == programme_id,
            Submission.manager_user_id == user_id,
            Submission.domain == OperationalDomain.OUTREACH,
        )
    )
    if for_update:
        query = query.with_for_update(of=(OutreachProgramme, Submission))
    row = db.execute(query).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Outreach programme not found.")
    return row[0], row[1], row[2]


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


@router.get("/periods", response_model=list[PeriodResponse])
def list_periods(request: Request, current: ManagerUser, db: DbSession) -> list[PeriodResponse]:
    _require_outreach(current)
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


@router.get("/outreach/current-period", response_model=CurrentPeriodResponse)
def get_current_period(
    request: Request, current: ManagerUser, db: DbSession
) -> CurrentPeriodResponse:
    _require_outreach(current)
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


@router.get("/outreach/programmes", response_model=list[OutreachProgrammeResponse])
def list_programmes(current: ManagerUser, db: DbSession) -> list[OutreachProgrammeResponse]:
    _require_outreach(current)
    rows = db.execute(
        select(OutreachProgramme, Submission, ReportingPeriod)
        .join(Submission, Submission.id == OutreachProgramme.submission_id)
        .join(ReportingPeriod, ReportingPeriod.id == Submission.reporting_period_id)
        .where(
            Submission.manager_user_id == current.user_id,
            Submission.domain == OperationalDomain.OUTREACH,
        )
        .order_by(OutreachProgramme.programme_date.desc(), OutreachProgramme.created_at.desc())
    ).all()
    return [_programme_response(db, *row) for row in rows]


@router.get("/outreach/programmes/{programme_id}", response_model=OutreachProgrammeResponse)
def get_programme(programme_id: UUID, current: ManagerUser, db: DbSession) -> OutreachProgrammeResponse:
    _require_outreach(current)
    return _programme_response(db, *_owned_programme(db, current.user_id, programme_id))


@router.post("/outreach/programmes", response_model=OutreachProgrammeResponse, status_code=201)
def create_programme(
    payload: OutreachProgrammeCreate,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> OutreachProgrammeResponse:
    _require_outreach(current)
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_current_period_for_create(payload.reporting_period_id, period)
    if not period.period_start <= payload.programme_date <= period.period_end:
        raise HTTPException(status_code=422, detail="Programme date must be inside the reporting period.")
    submission = db.scalar(
        select(Submission).where(
            Submission.domain == OperationalDomain.OUTREACH,
            Submission.reporting_period_id == period.id,
            Submission.status != SubmissionStatus.SUPERSEDED,
        ).with_for_update()
    )
    if submission is None:
        submission = Submission(
            domain=OperationalDomain.OUTREACH,
            manager_user_id=current.user_id,
            reporting_period_id=period.id,
            status=SubmissionStatus.DRAFT,
        )
        db.add(submission)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="An active submission already exists for this period.") from exc
    if submission.manager_user_id != current.user_id:
        raise HTTPException(status_code=409, detail="This reporting-period submission belongs to another manager.")
    require_manager_mutation(submission, period)
    values = payload.model_dump(exclude={"reporting_period_id"})
    programme = OutreachProgramme(submission_id=submission.id, **values)
    db.add(programme)
    submission.row_version += 1
    db.flush()
    db.refresh(programme)
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="outreach.programme_created",
        target_type="outreach_programme",
        target_reference=str(programme.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return _programme_response(db, programme, submission, period)


@router.put("/outreach/programmes/{programme_id}", response_model=OutreachProgrammeResponse)
def update_programme(
    programme_id: UUID,
    payload: OutreachProgrammeUpdate,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> OutreachProgrammeResponse:
    _require_outreach(current)
    programme, submission, period = _owned_programme(db, current.user_id, programme_id, for_update=True)
    if payload.expected_row_version != submission.row_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stale_submission",
                "message": "This submission has changed. Refresh to load the latest version.",
                "current_row_version": submission.row_version,
            },
        )
    authoritative_period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, authoritative_period)
    if not period.period_start <= payload.programme_date <= period.period_end:
        raise HTTPException(status_code=422, detail="Programme date must be inside the reporting period.")
    for key, value in payload.model_dump(exclude={"reporting_period_id", "expected_row_version"}).items():
        setattr(programme, key, value)
    submission.row_version += 1
    db.flush()
    db.refresh(programme)
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="outreach.programme_updated",
        target_type="outreach_programme",
        target_reference=str(programme.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return _programme_response(db, programme, submission, period)


@router.delete("/outreach/programmes/{programme_id}", status_code=204)
def delete_programme(programme_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> Response:
    _require_outreach(current)
    programme, submission, _period = _owned_programme(db, current.user_id, programme_id, for_update=True)
    authoritative_period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, authoritative_period)
    db.delete(programme)
    submission.row_version += 1
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="outreach.programme_deleted",
        target_type="outreach_programme",
        target_reference=str(programme.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/outreach/submissions/{submission_id}/submit", response_model=MessageResponse)
def submit_outreach(submission_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> MessageResponse:
    _require_outreach(current)
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id,
            Submission.manager_user_id == current.user_id,
            Submission.domain == OperationalDomain.OUTREACH,
        ).with_for_update()
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Outreach submission not found.")
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, period)
    programmes = db.scalars(select(OutreachProgramme).where(OutreachProgramme.submission_id == submission.id)).all()
    if not programmes:
        raise HTTPException(status_code=422, detail="At least one programme is required.")
    previous = submission.status
    if previous == SubmissionStatus.CORRECTION_REQUESTED:
        submission.revision_number += 1
    submission.status = SubmissionStatus.SUBMITTED
    submission.submitted_at = datetime.now(UTC)
    submission.row_version += 1
    committed_evidence = commit_temporary_evidence(db, submission)
    db.add(
        ReviewAction(
            submission_id=submission.id,
            actor_user_id=current.user_id,
            action=ReviewActionType.SUBMIT,
            from_status=previous,
            to_status=SubmissionStatus.SUBMITTED,
            snapshot=submission_snapshot(db, submission),
        )
    )
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="outreach.submitted",
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
                "domain": submission.domain.value,
                "revision_number": submission.revision_number,
                "evidence_ids": [str(item.id) for item in committed_evidence],
            },
        )
    db.commit()
    return MessageResponse(message="Outreach submission sent for review.")


@router.get("/outreach/submissions", response_model=list[OutreachSubmissionSummary])
def outreach_history(current: ManagerUser, db: DbSession) -> list[OutreachSubmissionSummary]:
    _require_outreach(current)
    submissions = db.scalars(
        select(Submission)
        .where(
            Submission.manager_user_id == current.user_id,
            Submission.domain == OperationalDomain.OUTREACH,
        )
        .order_by(Submission.created_at.desc())
    ).all()
    result: list[OutreachSubmissionSummary] = []
    for submission in submissions:
        period = db.get(ReportingPeriod, submission.reporting_period_id)
        programmes = db.scalars(select(OutreachProgramme).where(OutreachProgramme.submission_id == submission.id)).all()
        if period is None:
            continue
        responses = [_programme_response(db, item, submission, period) for item in programmes]
        result.append(
            OutreachSubmissionSummary(
                id=submission.id,
                domain=submission.domain,
                reporting_period_id=period.id,
                reporting_period_label=f"{period.year}-{period.month:02d}",
                status=submission.status,
                revision_number=submission.revision_number,
                row_version=submission.row_version,
                submitted_at=submission.submitted_at,
                approved_at=submission.approved_at,
                correction_reason=correction_reason(db, submission.id),
                programme_count=len(responses),
                programmes=responses,
            )
        )
    return result
