from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OperationalDomain, RoleCode


class CreateManagerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._@-]+$")
    display_name: str = Field(min_length=1, max_length=160)
    temporary_password: str = Field(min_length=12, max_length=128)
    manager_domain: OperationalDomain

    @field_validator("temporary_password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("temporary password cannot contain only whitespace")
        return value


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temporary_password: str = Field(min_length=12, max_length=128)


class AdminUserResponse(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: RoleCode
    manager_domain: OperationalDomain | None
    is_active: bool
    must_change_password: bool
    failed_login_count: int
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    active_session_count: int

