from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
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


class PublicReleaseMetadata(Base):
    """Classification and public visibility, kept outside the frozen payload.

    The payload and its checksum stay immutable; this row only says whether a
    release is official institutional data and whether it may be served
    publicly. A release without a row is official and publicly visible, so
    the normal Prepare -> Publish workflow needs no extra step.
    """

    __tablename__ = "public_release_metadata"
    __table_args__ = (
        CheckConstraint("classification in ('official', 'test')", name="classification_allowed"),
        CheckConstraint("classification = 'official' or public_visible = false", name="test_never_public"),
        CheckConstraint("length(trim(reason)) > 0", name="reason_required"),
        {"schema": "publication"},
    )

    release_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publication.public_releases.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    public_visible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Certificate(Base):
    """A supporting public document (migration 0017), for example an e-waste disposal certificate.

    Not a sustainability metric input: ``quantity_value`` is document metadata
    only and no calculation, resolver or release reads this table. The file is
    kept in the dedicated certificate storage root under ``storage_key``.
    ``reporting_year`` is entered explicitly and is never derived from
    ``certificate_date``.
    """

    __tablename__ = "certificates"
    __table_args__ = (
        Index("ix_certificates_public_lookup", "domain", "reporting_year", "status"),
        {"schema": "publication"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    certificate_type: Mapped[str] = mapped_column(Text, nullable=False)
    reporting_year: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    issuer: Mapped[str | None] = mapped_column(Text)
    registration_id: Mapped[str | None] = mapped_column(Text)
    authorization_no: Mapped[str | None] = mapped_column(Text)
    serial_no: Mapped[str | None] = mapped_column(Text)
    certificate_date: Mapped[date | None] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    invoice_no: Mapped[str | None] = mapped_column(Text)
    manifest_doc_no: Mapped[str | None] = mapped_column(Text)
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    quantity_unit: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
