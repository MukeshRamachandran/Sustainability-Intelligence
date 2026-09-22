from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select, update

from app.core.config import Settings
from app.models.enums import OperationalDomain, RoleCode
from app.models.identity import (
    ManagerDomainAssignment,
    Role,
    SessionRecord,
    User,
    UserRoleAssignment,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    SessionResponse,
    SessionUser,
)
from app.security.dependencies import AuthContext, AuthenticatedUser, CsrfUser, DbSession
from app.security.passwords import (
    consume_dummy_password_check,
    hash_password,
    password_needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.security.tokens import new_opaque_token, token_hash
from app.services.audit import add_audit_log

router = APIRouter(prefix="/api/auth", tags=["authentication"])
INVALID_LOGIN = "Invalid username or password."


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _set_auth_cookies(response: Response, settings: Settings, session_token: str, csrf_token: str) -> None:
    max_age = settings.SESSION_ABSOLUTE_HOURS * 60 * 60
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
        max_age=max_age,
    )
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
        max_age=max_age,
    )
    response.headers["X-CSRF-Token"] = csrf_token


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")


def _session_user(current: AuthContext) -> SessionUser:
    return SessionUser(
        id=current.user_id,
        username=current.username,
        display_name=current.display_name,
        role=current.role,
        manager_domain=current.manager_domain,
        must_change_password=current.must_change_password,
    )


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> SessionResponse:
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(User.normalized_username == _normalize(payload.username)))
    if user is None:
        consume_dummy_password_check(payload.password)
        add_audit_log(
            db,
            actor_user_id=None,
            actor_type="anonymous",
            event_type="auth.login",
            target_type="user",
            target_reference=None,
            outcome="denied",
            request_id=_request_id(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN)

    locked = user.locked_until is not None and user.locked_until > now
    valid = not locked and user.is_active and verify_password(user.password_hash, payload.password)
    if not valid:
        if not locked:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
                user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
        add_audit_log(
            db,
            actor_user_id=user.id,
            actor_type="user",
            event_type="auth.login",
            target_type="user",
            target_reference=str(user.id),
            outcome="denied",
            request_id=_request_id(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN)

    access = db.execute(
        select(Role.code, ManagerDomainAssignment.domain)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
        .outerjoin(
            ManagerDomainAssignment,
            (ManagerDomainAssignment.user_id == UserRoleAssignment.user_id)
            & (ManagerDomainAssignment.revoked_at.is_(None)),
        )
        .where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.revoked_at.is_(None))
    ).one_or_none()
    if access is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account access is not configured.")
    role_code, manager_domain = access
    role = RoleCode(role_code)
    if (role is RoleCode.MANAGER) != (manager_domain is not None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account access is not configured.")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    raw_session = new_opaque_token()
    raw_csrf = new_opaque_token()
    record = SessionRecord(
        user_id=user.id,
        session_token_hash=token_hash(raw_session),
        csrf_secret_hash=token_hash(raw_csrf),
        last_seen_at=now,
        idle_expires_at=now + timedelta(minutes=settings.SESSION_IDLE_MINUTES),
        absolute_expires_at=now + timedelta(hours=settings.SESSION_ABSOLUTE_HOURS),
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    db.add(record)
    add_audit_log(
        db,
        actor_user_id=user.id,
        actor_type="user",
        event_type="auth.login",
        target_type="session",
        target_reference=str(record.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    _set_auth_cookies(response, settings, raw_session, raw_csrf)
    return SessionResponse(
        user=SessionUser(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=role,
            manager_domain=OperationalDomain(manager_domain) if manager_domain else None,
            must_change_password=user.must_change_password,
        )
    )


@router.get("/session", response_model=SessionResponse)
def get_session(current: AuthenticatedUser) -> SessionResponse:
    return SessionResponse(user=_session_user(current))


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, current: CsrfUser, db: DbSession) -> MessageResponse:
    now = datetime.now(UTC)
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.id == current.session_id)
        .values(revoked_at=now, revoked_reason="user_logout")
    )
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type="auth.logout",
        target_type="session",
        target_reference=str(current.session_id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    _clear_auth_cookies(response, request.app.state.settings)
    return MessageResponse(message="Logged out.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    settings: Settings = request.app.state.settings
    try:
        validate_password_policy(payload.new_password, settings.PASSWORD_MIN_LENGTH)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="New password does not meet policy.") from exc
    user = db.get(User, current.user_id)
    if user is None or not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    if verify_password(user.password_hash, payload.new_password):
        raise HTTPException(status_code=422, detail="New password must be different.")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(UTC)
    db.execute(
        update(SessionRecord)
        .where(
            SessionRecord.user_id == user.id,
            SessionRecord.id != current.session_id,
            SessionRecord.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC), revoked_reason="password_changed")
    )
    add_audit_log(
        db,
        actor_user_id=user.id,
        actor_type="user",
        event_type="auth.password_changed",
        target_type="user",
        target_reference=str(user.id),
        outcome="succeeded",
        request_id=_request_id(request),
    )
    db.commit()
    return MessageResponse(message="Password changed.")
