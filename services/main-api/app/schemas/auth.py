from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import OperationalDomain, RoleCode


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        return value.strip()


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class SessionUser(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: RoleCode
    manager_domain: OperationalDomain | None
    must_change_password: bool


class SessionResponse(BaseModel):
    authenticated: bool = True
    user: SessionUser


class MessageResponse(BaseModel):
    message: str
