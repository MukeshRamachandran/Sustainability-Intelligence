from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import (
    ACCOUNTING_CLASSIFICATION_DB,
    FACTOR_SET_STATUS_DB,
    OPERATIONAL_DOMAIN_DB,
    PUBLICATION_CLASS_DB,
    REVIEW_ACTION_TYPE_DB,
    SUBMISSION_STATUS_DB,
    AccountingClassification,
    FactorSetStatus,
    OperationalDomain,
    PublicationClass,
    ReviewActionType,
    SubmissionStatus,
)


class ReportingPeriod(Base):
    __tablename__ = "reporting_periods"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_reporting_period_year_month"),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InstitutionalPopulationReference(Base):
    """Owner-approved population reference selected by reporting year."""

    __tablename__ = "institutional_population_references"
    __table_args__ = (
        CheckConstraint("population >= 0", name="population_non_negative"),
        CheckConstraint("unit = 'people'", name="population_unit_people"),
        CheckConstraint("length(trim(source_reference)) > 0", name="population_source_required"),
        {"schema": "sustainability"},
    )

    effective_year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="people")
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"
    __table_args__ = (
        CheckConstraint(
            "min_value is null or max_value is null or min_value <= max_value",
            name="metric_range_valid",
        ),
        CheckConstraint(
            "manager_editable or calculation_method is not null",
            name="calculated_metric_has_method",
        ),
        {"schema": "sustainability"},
    )

    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    operational_domain: Mapped[OperationalDomain] = mapped_column(OPERATIONAL_DOMAIN_DB, nullable=False, index=True)
    accounting_classification: Mapped[AccountingClassification] = mapped_column(
        ACCOUNTING_CLASSIFICATION_DB, nullable=False
    )
    canonical_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    required_for_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    zero_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    manager_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    calculation_method: Mapped[str | None] = mapped_column(Text)
    publication_class: Mapped[PublicationClass] = mapped_column(PUBLICATION_CLASS_DB, nullable=False)
    factor_code: Mapped[str | None] = mapped_column(String(80))
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index(
            "uq_active_submission_domain_period",
            "domain",
            "reporting_period_id",
            unique=True,
            postgresql_where=text("status <> 'superseded'"),
        ),
        CheckConstraint("revision_number > 0", name="submission_revision_positive"),
        CheckConstraint("row_version > 0", name="submission_row_version_positive"),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    domain: Mapped[OperationalDomain] = mapped_column(OPERATIONAL_DOMAIN_DB, nullable=False, index=True)
    manager_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False
    )
    reporting_period_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.reporting_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        SUBMISSION_STATUS_DB, nullable=False, default=SubmissionStatus.DRAFT
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    remarks: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT")
    )
    superseded_submission_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sustainability.submissions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SubmissionValue(Base):
    __tablename__ = "submission_values"
    __table_args__ = ({"schema": "sustainability"},)

    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.submissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    metric_code: Mapped[str] = mapped_column(
        ForeignKey("sustainability.metric_definitions.code", ondelete="RESTRICT"), primary_key=True
    )
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    canonical_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    quality_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = ({"schema": "sustainability"},)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[ReviewActionType] = mapped_column(REVIEW_ACTION_TYPE_DB, nullable=False)
    from_status: Mapped[SubmissionStatus | None] = mapped_column(SUBMISSION_STATUS_DB)
    to_status: Mapped[SubmissionStatus] = mapped_column(SUBMISSION_STATUS_DB, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionEvidence(Base):
    __tablename__ = "submission_evidence"
    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="evidence_file_size_positive"),
        CheckConstraint("revision_number > 0", name="evidence_revision_positive"),
        Index("ix_submission_evidence_submission_uploaded", "submission_id", "uploaded_at"),
        Index("ix_submission_evidence_submission_committed", "submission_id", "committed_at"),
        Index("ix_submission_evidence_uploader", "uploaded_by_user_id"),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric_code: Mapped[str | None] = mapped_column(
        ForeignKey("sustainability.metric_definitions.code", ondelete="RESTRICT")
    )
    evidence_category: Mapped[str | None] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sustainability.submission_evidence.id", ondelete="RESTRICT")
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutreachProgramme(Base):
    __tablename__ = "outreach_programmes"
    __table_args__ = (
        CheckConstraint("length(btrim(programme_name)) > 0", name="outreach_programme_name_required"),
        CheckConstraint("length(btrim(theme)) > 0", name="outreach_theme_required"),
        CheckConstraint(
            "theme in ('climate_smart_agriculture','climate_change','afforestation',"
            "'water_conservation','waste_management','biodiversity_conservation','hwcc',"
            "'livelihood_development','campus_sustainability','other')",
            name="outreach_theme_allowed",
        ),
        CheckConstraint(
            "theme <> 'other' or (other_theme is not null and length(btrim(other_theme)) > 0)",
            name="outreach_other_theme_required",
        ),
        CheckConstraint(
            "coalesce(male_participants,0) + coalesce(female_participants,0) + "
            "coalesce(other_not_disclosed_participants,0) <= participant_total",
            name="outreach_gender_not_above_total",
        ),
        CheckConstraint(
            "coalesce(waste_collected_kg,0) >= 0 and coalesce(species_identified_count,0) >= 0",
            name="outreach_internal_impact_nonnegative",
        ),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    programme_name: Mapped[str] = mapped_column(String(300), nullable=False)
    programme_date: Mapped[date] = mapped_column(Date, nullable=False)
    theme: Mapped[str] = mapped_column(String(80), nullable=False)
    other_theme: Mapped[str | None] = mapped_column(String(200))
    partner_organisation: Mapped[str | None] = mapped_column(String(300))
    programme_location: Mapped[str | None] = mapped_column(String(300))
    programme_description: Mapped[str | None] = mapped_column(Text)
    school_students: Mapped[int | None] = mapped_column(Integer)
    college_students: Mapped[int | None] = mapped_column(Integer)
    farmers_agriculture: Mapped[int | None] = mapped_column(Integer)
    industrial_experts: Mapped[int | None] = mapped_column(Integer)
    researchers_experts: Mapped[int | None] = mapped_column(Integer)
    government_participants: Mapped[int | None] = mapped_column(Integer)
    participant_total: Mapped[int] = mapped_column(
        Integer,
        Computed(
            "coalesce(school_students,0) + coalesce(college_students,0) + "
            "coalesce(farmers_agriculture,0) + coalesce(industrial_experts,0) + "
            "coalesce(researchers_experts,0) + coalesce(government_participants,0)",
            persisted=True,
        ),
    )
    # LEGACY / AUDIT ONLY. Outreach is no longer reported by gender: these three
    # columns are never written by new submissions, never aggregated and never
    # published. They are kept so older programme rows stay intact.
    male_participants: Mapped[int | None] = mapped_column(Integer)
    female_participants: Mapped[int | None] = mapped_column(Integer)
    other_not_disclosed_participants: Mapped[int | None] = mapped_column(Integer)
    saplings_planted: Mapped[int | None] = mapped_column(Integer)
    waste_collected_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    species_identified_count: Mapped[int | None] = mapped_column(Integer)
    species_details: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    species_verification_notes: Mapped[str | None] = mapped_column(Text)
    experts_involved: Mapped[int | None] = mapped_column(Integer)
    volunteers_engaged: Mapped[int | None] = mapped_column(Integer)
    volunteer_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WasteCategory(Base):
    __tablename__ = "waste_categories"
    __table_args__ = ({"schema": "sustainability"},)

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WasteMaterial(Base):
    __tablename__ = "waste_materials"
    __table_args__ = (
        Index("ix_waste_materials_category", "category_code"),
        {"schema": "sustainability"},
    )

    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category_code: Mapped[str] = mapped_column(
        ForeignKey("sustainability.waste_categories.code", ondelete="RESTRICT"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WasteSubmissionItem(Base):
    """One dry-waste material row on a Waste submission.

    Category is never stored here: it is derived from the material's catalog
    entry, so a row cannot claim material Iron under category Plastic.
    """

    __tablename__ = "waste_submission_items"
    __table_args__ = (
        UniqueConstraint("submission_id", "material_code", name="uq_waste_item_submission_material"),
        CheckConstraint("quantity_kg > 0", name="waste_item_quantity_positive"),
        Index("ix_waste_items_submission", "submission_id"),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_code: Mapped[str] = mapped_column(
        ForeignKey("sustainability.waste_materials.code", ondelete="RESTRICT"), nullable=False
    )
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EmissionFactorSet(Base):
    __tablename__ = "emission_factor_sets"
    __table_args__ = ({"schema": "sustainability"},)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[FactorSetStatus] = mapped_column(FACTOR_SET_STATUS_DB, nullable=False, default=FactorSetStatus.DRAFT)
    source_note: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT")
    )
    activated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmissionFactor(Base):
    __tablename__ = "emission_factors"
    __table_args__ = (
        UniqueConstraint("factor_set_id", "code", name="uq_factor_set_code"),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    factor_set_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.emission_factor_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    factor_value: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    activity_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    result_unit: Mapped[str] = mapped_column(String(40), nullable=False, default="kgCO2e")
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class CalculationParameter(Base):
    """Governed, effective-dated conversion parameter that is not an emission factor
    (for example DG specific fuel consumption, L/kWh). Append-only: a change is a
    new row with a later ``effective_from``."""

    __tablename__ = "calculation_parameters"
    __table_args__ = (
        UniqueConstraint("code", "effective_from", name="uq_calculation_parameter_code_effective"),
        CheckConstraint("parameter_value >= 0", name="calculation_parameter_non_negative"),
        CheckConstraint("length(trim(source_reference)) > 0", name="calculation_parameter_source_required"),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    parameter_value: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalculationResult(Base):
    __tablename__ = "calculation_results"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "submission_revision", "calculation_code",
            name="uq_calculation_submission_revision_code",
        ),
        {"schema": "sustainability"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.submissions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric_code: Mapped[str | None] = mapped_column(String(100))
    submission_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    calculation_code: Mapped[str] = mapped_column(String(100), nullable=False)
    calculation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    unavailable_reason: Mapped[str | None] = mapped_column(String(100))
    activity_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    activity_unit: Mapped[str | None] = mapped_column(String(40))
    factor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sustainability.emission_factors.id", ondelete="RESTRICT"),
    )
    factor_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    factor_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sustainability.emission_factor_sets.id", ondelete="RESTRICT")
    )
    factor_set_version: Mapped[str | None] = mapped_column(String(100))
    factor_code: Mapped[str | None] = mapped_column(String(80))
    factor_unit: Mapped[str | None] = mapped_column(String(80))
    result_kgco2e: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    result_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    result_unit: Mapped[str | None] = mapped_column(String(40))
    formula_version: Mapped[str] = mapped_column(String(80), nullable=False)
    # Frozen derivation behind a result whose activity is derived from another
    # source (kWh-based DG: source kWh, SFC applied, derived litres). 0015.
    derivation: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
