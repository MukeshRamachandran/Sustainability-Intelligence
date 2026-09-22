from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import OPERATIONAL_DOMAIN_DB, OperationalDomain


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_identity_users_normalized_email",
            "normalized_email",
            unique=True,
            postgresql_where=text("normalized_email is not null"),
        ),
        {"schema": "identity"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = ({"schema": "identity"},)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        Index(
            "uq_identity_one_active_role_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at is null"),
        ),
        CheckConstraint("length(trim(reason)) > 0", name="role_assignment_reason_required"),
        {"schema": "identity"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.roles.id", ondelete="RESTRICT"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class ManagerDomainAssignment(Base):
    __tablename__ = "manager_domain_assignments"
    __table_args__ = (
        Index(
            "uq_identity_one_active_domain_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at is null"),
        ),
        CheckConstraint("length(trim(reason)) > 0", name="domain_assignment_reason_required"),
        {"schema": "identity"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[OperationalDomain] = mapped_column(OPERATIONAL_DOMAIN_DB, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class SessionRecord(Base):
    __tablename__ = "sessions"
    __table_args__ = ({"schema": "identity"},)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
