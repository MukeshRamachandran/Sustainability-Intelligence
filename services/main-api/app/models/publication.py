from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import RELEASE_STATUS_DB, ReleaseStatus


class PublicRelease(Base):
    __tablename__ = "public_releases"
    __table_args__ = (
        Index(
            "uq_publication_one_active_release",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        {"schema": "publication"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[ReleaseStatus] = mapped_column(RELEASE_STATUS_DB, nullable=False, default=ReleaseStatus.CANDIDATE)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prepared_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False
    )
    published_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    reporting_period_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sustainability.reporting_periods.id", ondelete="RESTRICT")
    )


class PublicReleasePayload(Base):
    __tablename__ = "public_release_payloads"
    __table_args__ = ({"schema": "publication"},)

    release_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publication.public_releases.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
