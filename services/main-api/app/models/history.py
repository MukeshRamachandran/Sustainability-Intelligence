"""Historical sustainability data layer (0011_historical_data_layer).

Historical institutional records never went through the Manager/Admin
workflow, so they live here - never in submissions. Every stored value keeps
its true granularity (MONTHLY / YTD / ANNUAL / STATIC) and is traceable to an
immutable import batch and the raw source row it came from.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.db.base import Base

GRANULARITIES = ("MONTHLY", "YTD", "ANNUAL", "STATIC")
BATCH_STATUSES = ("STAGED", "RECONCILED", "VERIFIED", "REJECTED")
VERIFICATION_STATUSES = ("UNVERIFIED", "VERIFIED", "REJECTED", "CONFLICT")
AUTHORITY_STATUSES = ("SOURCE_REPORTED", "NORMALIZED", "AUTHORITATIVE")
VALUE_QUALIFIERS = ("EXACT", "AT_LEAST", "APPROXIMATE")
RESOLUTION_STATUSES = ("UNRESOLVED", "RESOLVED", "REJECTED_SOURCE")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(value) for value in values)})"


class HistoricalImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("source_sha256", "mapping_code", "mapping_version", name="source_mapping"),
        CheckConstraint(_in("status", BATCH_STATUSES), name="status_allowed"),
        CheckConstraint("length(source_sha256) = 64", name="sha256_length"),
        {"schema": "history"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Repository-relative reference only; never an absolute host path.
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_domain: Mapped[str] = mapped_column(String(40), nullable=False)
    mapping_code: Mapped[str] = mapped_column(String(100), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricalSourceRow(Base):
    __tablename__ = "source_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="batch_row"),
        {"schema": "history"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.import_batches.id", ondelete="RESTRICT"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricalPeriod(Base):
    __tablename__ = "periods"
    __table_args__ = (
        UniqueConstraint("granularity", "coverage_start", "coverage_end", name="granularity_coverage"),
        CheckConstraint(_in("granularity", GRANULARITIES), name="granularity_allowed"),
        CheckConstraint("coverage_end >= coverage_start", name="coverage_ordered"),
        CheckConstraint(
            "(granularity = 'MONTHLY' and month between 1 and 12) or (granularity <> 'MONTHLY' and month is null)",
            name="month_only_for_monthly",
        ),
        {"schema": "history"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int | None] = mapped_column(SmallInteger)
    granularity: Mapped[str] = mapped_column(String(10), nullable=False)
    coverage_start: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_end: Mapped[date] = mapped_column(Date, nullable=False)
    display_label: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricalMetricValue(Base):
    __tablename__ = "metric_values"
    __table_args__ = (
        UniqueConstraint(
            "period_id", "domain", "metric_code", "source_batch_id", "version", name="period_metric_batch_version"
        ),
        CheckConstraint(_in("verification_status", VERIFICATION_STATUSES), name="verification_allowed"),
        CheckConstraint(_in("authority_status", AUTHORITY_STATUSES), name="authority_allowed"),
        CheckConstraint(_in("value_qualifier", VALUE_QUALIFIERS), name="qualifier_allowed"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "authority_status <> 'AUTHORITATIVE' or verification_status = 'VERIFIED'",
            name="authoritative_requires_verified",
        ),
        {"schema": "history"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    period_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.periods.id", ondelete="RESTRICT"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_code: Mapped[str] = mapped_column(String(120), nullable=False)
    value_numeric: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    value_qualifier: Mapped[str] = mapped_column(String(20), nullable=False, default="EXACT")
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    source_batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.import_batches.id", ondelete="RESTRICT"), nullable=False
    )
    source_row_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.source_rows.id", ondelete="RESTRICT")
    )
    source_column: Mapped[str] = mapped_column(String(200), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    authority_status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.metric_values.id", ondelete="RESTRICT")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # False when the source reports only "<year> / to date": the value is
    # owner-confirmed but its coverage end month is unknown (0014).
    coverage_end_stated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricalCalculationResult(Base):
    __tablename__ = "calculation_results"
    __table_args__ = (
        UniqueConstraint("period_id", "calculation_code", "input_hash", name="period_calculation_input"),
        CheckConstraint("status in ('available', 'unavailable')", name="status_allowed"),
        CheckConstraint(
            "(status = 'available' and result_value is not null) or (status = 'unavailable' and result_value is null)",
            name="value_matches_status",
        ),
        {"schema": "history"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    period_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.periods.id", ondelete="RESTRICT"), nullable=False
    )
    calculation_code: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    unavailable_reason: Mapped[str | None] = mapped_column(String(160))
    result_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    result_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(80), nullable=False)
    factor_code: Mapped[str | None] = mapped_column(String(40))
    factor_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    factor_unit: Mapped[str | None] = mapped_column(String(40))
    factor_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sustainability.emission_factor_sets.id", ondelete="RESTRICT")
    )
    factor_set_version: Mapped[str | None] = mapped_column(String(100))
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricalConflict(Base):
    __tablename__ = "conflicts"
    __table_args__ = (
        UniqueConstraint("conflict_key", name="conflict_key"),
        CheckConstraint(_in("resolution_status", RESOLUTION_STATUSES), name="resolution_allowed"),
        CheckConstraint(
            "resolution_status = 'UNRESOLVED' or (resolution_reason is not null and resolved_at is not null)",
            name="resolution_documented",
        ),
        {"schema": "history"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conflict_key: Mapped[str] = mapped_column(String(300), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(60), nullable=False)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_code: Mapped[str] = mapped_column(String(120), nullable=False)
    period_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.periods.id", ondelete="RESTRICT"), nullable=False
    )
    source_a_batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.import_batches.id", ondelete="RESTRICT"), nullable=False
    )
    value_a: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    source_b_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.import_batches.id", ondelete="RESTRICT")
    )
    value_b: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNRESOLVED")
    chosen_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("history.import_batches.id", ondelete="RESTRICT")
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
