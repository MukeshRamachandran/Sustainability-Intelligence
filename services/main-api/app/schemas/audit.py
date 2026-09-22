from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    timestamp: datetime
    actor_user_id: UUID | None
    actor_username: str | None
    actor_display_name: str | None
    actor_type: str
    action: str
    domain: str | None
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    metadata: dict[str, object]


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    page: int
    page_size: int
    total: int
    pages: int

