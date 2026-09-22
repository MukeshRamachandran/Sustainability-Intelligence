from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.models.audit import AuditLog
from app.models.enums import OperationalDomain
from app.models.identity import User
from app.schemas.audit import AuditLogPage, AuditLogResponse
from app.security.dependencies import AdminUser, DbSession

router = APIRouter(prefix="/api/admin/audit-logs", tags=["admin audit"])
SENSITIVE_PARTS = ("password", "secret", "token", "csrf", "hash", "storage", "path", "content")


def _safe_metadata(value: object, depth: int = 0) -> object:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key): _safe_metadata(item, depth + 1)
            for key, item in value.items()
            if not any(part in str(key).casefold() for part in SENSITIVE_PARTS)
        }
    if isinstance(value, list):
        return [_safe_metadata(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)[:1000]


def _domain(event_type: str, metadata: dict[str, object]) -> str | None:
    configured = metadata.get("domain")
    if isinstance(configured, str) and configured in {item.value for item in OperationalDomain}:
        return configured
    prefix = event_type.partition(".")[0]
    return prefix if prefix in {item.value for item in OperationalDomain} else None


@router.get("", response_model=AuditLogPage)
def audit_logs(
    current: AdminUser,
    db: DbSession,
    action: str | None = Query(default=None, max_length=120),
    user: str | None = Query(default=None, min_length=1, max_length=160),
    user_id: UUID | None = None,
    domain: OperationalDomain | None = None,
    resource_type: str | None = Query(default=None, max_length=80),
    resource_id: str | None = Query(default=None, max_length=200),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AuditLogPage:
    filters = []
    if action:
        filters.append(AuditLog.event_type == action)
    if user_id:
        filters.append(AuditLog.actor_user_id == user_id)
    if user:
        matched_users = select(User.id).where(
            or_(User.username.ilike(f"%{user}%"), User.display_name.ilike(f"%{user}%"))
        )
        filters.append(AuditLog.actor_user_id.in_(matched_users))
    if domain:
        filters.append(
            or_(
                AuditLog.event_type.like(f"{domain.value}.%"),
                AuditLog.safe_metadata["domain"].as_string() == domain.value,
            )
        )
    if resource_type:
        filters.append(AuditLog.target_type == resource_type)
    if resource_id:
        filters.append(AuditLog.target_reference == resource_id)
    if date_from:
        filters.append(AuditLog.created_at >= date_from)
    if date_to:
        filters.append(AuditLog.created_at <= date_to)

    total = int(db.scalar(select(func.count(AuditLog.id)).where(*filters)) or 0)
    rows = db.execute(
        select(AuditLog, User.username, User.display_name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for item, username, display_name in rows:
        sanitized = _safe_metadata(item.safe_metadata)
        metadata = sanitized if isinstance(sanitized, dict) else {}
        items.append(
            AuditLogResponse(
                id=item.id,
                timestamp=item.created_at,
                actor_user_id=item.actor_user_id,
                actor_username=username,
                actor_display_name=display_name,
                actor_type=item.actor_type,
                action=item.event_type,
                domain=_domain(item.event_type, metadata),
                resource_type=item.target_type,
                resource_id=item.target_reference,
                outcome=item.outcome,
                request_id=item.request_id,
                metadata=metadata,
            )
        )
    return AuditLogPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=ceil(total / page_size) if total else 0,
    )
