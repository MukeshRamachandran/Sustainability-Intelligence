from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def add_audit_log(
    db: Session,
    *,
    actor_user_id: UUID | None,
    actor_type: str,
    event_type: str,
    target_type: str,
    target_reference: str | None,
    outcome: str,
    request_id: str | None,
    metadata: dict[str, object] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            event_type=event_type,
            target_type=target_type,
            target_reference=target_reference,
            outcome=outcome,
            request_id=request_id,
            safe_metadata=metadata or {},
        )
    )
