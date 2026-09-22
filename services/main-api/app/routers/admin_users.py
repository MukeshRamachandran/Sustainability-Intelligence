from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models.enums import RoleCode
from app.models.identity import ManagerDomainAssignment, Role, SessionRecord, User, UserRoleAssignment
from app.schemas.admin_users import AdminUserResponse, CreateManagerRequest, ResetPasswordRequest
from app.schemas.auth import MessageResponse
from app.security.dependencies import AdminUser, CsrfUser, DbSession, require_admin
from app.security.passwords import hash_password, validate_password_policy
from app.services.audit import add_audit_log

router = APIRouter(prefix="/api/admin/users", tags=["admin user management"])


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _admin(current: CsrfUser) -> None:
    require_admin(current)


def _locked_user(db: DbSession, user_id: UUID) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _revoke_sessions(db: DbSession, user_id: UUID, reason: str) -> int:
    active_count = int(
        db.scalar(
            select(func.count(SessionRecord.id)).where(
                SessionRecord.user_id == user_id,
                SessionRecord.revoked_at.is_(None),
            )
        )
        or 0
    )
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user_id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    return active_count


def _user_rows(db: DbSession, user_id: UUID | None = None) -> list[AdminUserResponse]:
    active_sessions = (
        select(SessionRecord.user_id, func.count(SessionRecord.id).label("active_session_count"))
        .where(SessionRecord.revoked_at.is_(None), SessionRecord.absolute_expires_at > datetime.now(UTC))
        .group_by(SessionRecord.user_id)
        .subquery()
    )
    query = (
        select(
            User,
            Role.code,
            ManagerDomainAssignment.domain,
            func.coalesce(active_sessions.c.active_session_count, 0),
        )
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .outerjoin(
            ManagerDomainAssignment,
            (ManagerDomainAssignment.user_id == User.id) & (ManagerDomainAssignment.revoked_at.is_(None)),
        )
        .outerjoin(active_sessions, active_sessions.c.user_id == User.id)
        .where(UserRoleAssignment.revoked_at.is_(None))
        .order_by(User.username)
    )
    if user_id is not None:
        query = query.where(User.id == user_id)
    return [
        AdminUserResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=RoleCode(role_code),
            manager_domain=manager_domain,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            failed_login_count=user.failed_login_count,
            locked_until=user.locked_until,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            active_session_count=active_session_count,
        )
        for user, role_code, manager_domain, active_session_count in db.execute(query).all()
    ]


@router.get("", response_model=list[AdminUserResponse])
def list_users(current: AdminUser, db: DbSession) -> list[AdminUserResponse]:
    return _user_rows(db)


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_manager(
    payload: CreateManagerRequest,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> AdminUserResponse:
    _admin(current)
    try:
        validate_password_policy(payload.temporary_password, request.app.state.settings.PASSWORD_MIN_LENGTH)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Temporary password does not meet policy.") from exc
    normalized = payload.username.casefold()
    if db.scalar(select(User.id).where(User.normalized_username == normalized)) is not None:
        raise HTTPException(status_code=409, detail="Username already exists.")
    manager_role = db.scalar(select(Role).where(Role.code == RoleCode.MANAGER.value))
    if manager_role is None:
        raise HTTPException(status_code=500, detail="Manager role is not configured.")
    user = User(
        username=payload.username,
        normalized_username=normalized,
        display_name=payload.display_name,
        password_hash=hash_password(payload.temporary_password),
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=manager_role.id, reason="administrator account creation"))
    db.flush()
    db.add(
        ManagerDomainAssignment(
            user_id=user.id,
            domain=payload.manager_domain,
            reason="administrator account creation",
        )
    )
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="admin.user_created",
        target_type="user",
        target_reference=str(user.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"role": RoleCode.MANAGER.value, "domain": payload.manager_domain.value},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint_name = getattr(getattr(exc, "orig", None), "diag", None)
        if getattr(constraint_name, "constraint_name", None) == "users_normalized_username_key":
            raise HTTPException(status_code=409, detail="Username already exists.") from exc
        raise
    return _user_rows(db, user.id)[0]


@router.post("/{user_id}/reset-password", response_model=MessageResponse)
def reset_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    _admin(current)
    try:
        validate_password_policy(payload.temporary_password, request.app.state.settings.PASSWORD_MIN_LENGTH)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Temporary password does not meet policy.") from exc
    user = _locked_user(db, user_id)
    user.password_hash = hash_password(payload.temporary_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    user.password_changed_at = datetime.now(UTC)
    revoked = _revoke_sessions(db, user.id, "administrator_password_reset")
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="admin.password_reset",
        target_type="user",
        target_reference=str(user.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"sessions_revoked": revoked},
    )
    db.commit()
    return MessageResponse(message="Password reset. The user must change it at next sign-in.")


@router.post("/{user_id}/deactivate", response_model=MessageResponse)
def deactivate_user(
    user_id: UUID,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    _admin(current)
    if user_id == current.user_id:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")
    user = _locked_user(db, user_id)
    role_code = db.scalar(
        select(Role.code)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
        .where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.revoked_at.is_(None))
    )
    if role_code == RoleCode.ADMIN.value:
        active_admins = db.scalar(
            select(func.count(User.id))
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(User.is_active.is_(True), UserRoleAssignment.revoked_at.is_(None), Role.code == RoleCode.ADMIN.value)
        )
        if int(active_admins or 0) <= 1:
            raise HTTPException(status_code=409, detail="The final active administrator cannot be deactivated.")
    user.is_active = False
    revoked = _revoke_sessions(db, user.id, "administrator_deactivation")
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="admin.user_deactivated",
        target_type="user",
        target_reference=str(user.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"sessions_revoked": revoked},
    )
    db.commit()
    return MessageResponse(message="User deactivated and active sessions revoked.")


@router.post("/{user_id}/activate", response_model=MessageResponse)
def activate_user(
    user_id: UUID,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    _admin(current)
    user = _locked_user(db, user_id)
    user.is_active = True
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="admin.user_activated",
        target_type="user",
        target_reference=str(user.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return MessageResponse(message="User activated.")


@router.post("/{user_id}/revoke-sessions", response_model=MessageResponse)
def revoke_sessions(
    user_id: UUID,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    _admin(current)
    user = _locked_user(db, user_id)
    revoked = _revoke_sessions(db, user.id, "administrator_revocation")
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="admin.sessions_revoked",
        target_type="user",
        target_reference=str(user.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"sessions_revoked": revoked},
    )
    db.commit()
    return MessageResponse(message=f"Revoked {revoked} active session(s).")
