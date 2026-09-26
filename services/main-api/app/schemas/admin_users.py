from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OperationalDomain, RoleCode


class CreateManagerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._@-]+$")
    display_name: str = Field(min_length=1, max_length=160)
    temporary_password: str = Field(min_length=12, max_length=128)
    manager_domain: OperationalDomain = Field(validation_alias=AliasChoices("manager_domain", "domain"))
    email: str | None = Field(default=None, max_length=320)
    role: Literal["manager"] = "manager"

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().casefold()
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if "@" not in value or value.startswith("@") or value.endswith("@") or " " in value:
            raise ValueError("email must be an address")
        return value

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

