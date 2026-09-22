from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.models.enums import OperationalDomain, RoleCode
from app.models.identity import (
    ManagerDomainAssignment,
    Role,
    SessionRecord,
    User,
    UserRoleAssignment,
)
from app.security.tokens import token_hash


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    session_id: UUID
    username: str
    display_name: str
    role: RoleCode
    manager_domain: OperationalDomain | None
    must_change_password: bool


DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")


def require_authenticated_user(request: Request, db: DbSession) -> AuthContext:
    settings: Settings = request.app.state.settings
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        raise _unauthorized()

    row = db.execute(
        select(SessionRecord, User, Role.code, ManagerDomainAssignment.domain)
        .join(User, User.id == SessionRecord.user_id)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .outerjoin(
            ManagerDomainAssignment,
            (ManagerDomainAssignment.user_id == User.id) & (ManagerDomainAssignment.revoked_at.is_(None)),
        )
        .where(
            SessionRecord.session_token_hash == token_hash(raw_token),
            SessionRecord.revoked_at.is_(None),
            UserRoleAssignment.revoked_at.is_(None),
        )
    ).one_or_none()
    if row is None:
        raise _unauthorized()

    session_record, user, role_code, manager_domain = row
    now = datetime.now(UTC)
    if not user.is_active or session_record.idle_expires_at <= now or session_record.absolute_expires_at <= now:
        if session_record.revoked_at is None:
            session_record.revoked_at = now
            session_record.revoked_reason = "expired_or_inactive"
            db.commit()
        raise _unauthorized()

    session_record.last_seen_at = now
    session_record.idle_expires_at = min(
        now + timedelta(minutes=settings.SESSION_IDLE_MINUTES),
        session_record.absolute_expires_at,
    )
    db.commit()
    return AuthContext(
        user_id=user.id,
        session_id=session_record.id,
        username=user.username,
        display_name=user.display_name,
        role=RoleCode(role_code),
        manager_domain=OperationalDomain(manager_domain) if manager_domain else None,
        must_change_password=user.must_change_password,
    )


AuthenticatedUser = Annotated[AuthContext, Depends(require_authenticated_user)]


def require_csrf(request: Request, current: AuthenticatedUser, db: DbSession) -> AuthContext:
    settings: Settings = request.app.state.settings
    header_token = request.headers.get("X-CSRF-Token")
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if not header_token or not cookie_token or header_token != cookie_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    stored = db.scalar(select(SessionRecord.csrf_secret_hash).where(SessionRecord.id == current.session_id))
    if stored is None or stored != token_hash(header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    return current


CsrfUser = Annotated[AuthContext, Depends(require_csrf)]


def require_manager(current: AuthenticatedUser) -> AuthContext:
    if current.role is not RoleCode.MANAGER or current.manager_domain is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required.")
    if current.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required.")
    return current


def require_admin(current: AuthenticatedUser) -> AuthContext:
    if current.role is not RoleCode.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")
    if current.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required.")
    return current


ManagerUser = Annotated[AuthContext, Depends(require_manager)]
AdminUser = Annotated[AuthContext, Depends(require_admin)]


def enforce_manager_domain(current: AuthContext, domain: OperationalDomain) -> None:
    if current.role is not RoleCode.MANAGER or current.manager_domain is not domain:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager domain access denied.")
    if current.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required.")
