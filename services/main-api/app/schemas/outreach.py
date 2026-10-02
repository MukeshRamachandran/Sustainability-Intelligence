from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import OperationalDomain, SubmissionStatus

OutreachTheme = Literal[
    "climate_smart_agriculture",
    "climate_change",
    "afforestation",
    "water_conservation",
    "waste_management",
    "biodiversity_conservation",
    "hwcc",
    "livelihood_development",
    "campus_sustainability",
    "other",
]
OptionalCount = Annotated[int | None, Field(default=None, ge=0)]


class SpeciesDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    species_name: str = Field(min_length=1, max_length=200)
    count: int = Field(ge=0)


class PeriodResponse(BaseModel):
    id: UUID
    year: int
    month: int
    label: str
    is_open: bool


class CurrentPeriodResponse(PeriodResponse):
    is_current: Literal[True] = True


class OutreachProgrammeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reporting_period_id: UUID | None = None
    programme_name: str = Field(min_length=1, max_length=300)
    programme_date: date
    theme: OutreachTheme
    other_theme: str | None = Field(default=None, max_length=200)
    partner_organisation: str | None = Field(default=None, max_length=300)
    programme_location: str | None = Field(default=None, max_length=300)
    programme_description: str | None = Field(default=None, max_length=4000)
    school_students: OptionalCount
    college_students: OptionalCount
    farmers_agriculture: OptionalCount
    industrial_experts: OptionalCount
    researchers_experts: OptionalCount
    government_participants: OptionalCount
    saplings_planted: OptionalCount
    waste_collected_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    species_identified_count: OptionalCount
    species_details: list[SpeciesDetail] | None = None
    species_verification_notes: str | None = Field(default=None, max_length=4000)
    experts_involved: OptionalCount
    volunteers_engaged: OptionalCount
    volunteer_hours: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    remarks: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "other_theme",
        "partner_organisation",
        "programme_location",
        "programme_description",
        "remarks",
        "species_verification_notes",
        mode="after",
    )
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def validate_theme(self) -> "OutreachProgrammeWrite":
        if self.theme == "other" and not self.other_theme:
            raise ValueError("other_theme is required when theme is other")
        if self.theme != "other":
            self.other_theme = None
        return self


class OutreachProgrammeCreate(OutreachProgrammeWrite):
    reporting_period_id: UUID


class OutreachProgrammeUpdate(OutreachProgrammeWrite):
    reporting_period_id: None = None
    expected_row_version: int = Field(ge=1)


class OutreachProgrammeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submission_id: UUID
    reporting_period_id: UUID
    reporting_period_label: str
    programme_name: str
    programme_date: date
    theme: str
    other_theme: str | None
    partner_organisation: str | None
    programme_location: str | None
    programme_description: str | None
    school_students: int | None
    college_students: int | None
    farmers_agriculture: int | None
    industrial_experts: int | None
    researchers_experts: int | None
    government_participants: int | None
    participant_total: int
    saplings_planted: int | None
    waste_collected_kg: Decimal | None
    species_identified_count: int | None
    species_details: list[SpeciesDetail] | None
    species_verification_notes: str | None
    experts_involved: int | None
    volunteers_engaged: int | None
    volunteer_hours: Decimal | None
    remarks: str | None
    status: SubmissionStatus
    revision_number: int
    row_version: int
    submitted_at: datetime | None
    correction_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class OutreachSubmissionSummary(BaseModel):
    id: UUID
    domain: OperationalDomain
    reporting_period_id: UUID
    reporting_period_label: str
    status: SubmissionStatus
    revision_number: int
    row_version: int
    manager_display_name: str | None = None
    submitted_at: datetime | None
    approved_at: datetime | None
    correction_reason: str | None = None
    programme_count: int
    programmes: list[OutreachProgrammeResponse] = []


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=2000)


class ReleasePrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reporting_period_id: UUID
    version: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")


class ReleaseResponse(BaseModel):
    id: UUID
    version: str
    status: str
    checksum_sha256: str
    reporting_period_id: UUID | None
    payload: dict[str, object]


class ReleaseSummary(BaseModel):
    """Release metadata only: no payload, no preparer/publisher identity."""

    id: UUID
    version: str
    status: str
    checksum_sha256: str
    reporting_period_id: UUID | None
    created_at: datetime
    published_at: datetime | None
