from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import OperationalDomain, ReviewActionType, SubmissionStatus
from app.schemas.emission_factors import CalculationResponse
from app.schemas.waste import WasteItemWrite, WasteSummaryResponse


class MetricValueWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    metric_code: str = Field(min_length=1, max_length=100)
    value: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    quality_note: str | None = Field(default=None, max_length=1000)

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("metric values must be finite")
        return value


class SubmissionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reporting_period_id: UUID | None = None
    remarks: str | None = Field(default=None, max_length=4000)
    values: list[MetricValueWrite]
    # Waste only. An empty list is a legitimate "no dry waste this month"; the
    # backend then derives dry_waste_generated_kg = 0.
    waste_items: list[WasteItemWrite] | None = None

    @model_validator(mode="after")
    def unique_metrics(self) -> "SubmissionWrite":
        codes = [item.metric_code for item in self.values]
        if len(codes) != len(set(codes)):
            raise ValueError("metric_code values must be unique")
        if self.waste_items is not None:
            materials = [item.material_code for item in self.waste_items]
            if len(materials) != len(set(materials)):
                raise ValueError("waste material_code values must be unique")
        return self


class SubmissionCreate(SubmissionWrite):
    reporting_period_id: UUID
    expected_row_version: int | None = Field(default=None, ge=1)


class SubmissionUpdate(SubmissionWrite):
    reporting_period_id: None = None
    expected_row_version: int = Field(ge=1)


class MetricDefinitionResponse(BaseModel):
    code: str
    display_name: str
    canonical_unit: str
    required_for_complete: bool
    zero_allowed: bool
    manager_editable: bool
    display_order: int


class MetricValueResponse(BaseModel):
    metric_code: str
    value: Decimal | None
    canonical_unit: str
    quality_note: str | None


class ReviewActionResponse(BaseModel):
    action: ReviewActionType
    from_status: SubmissionStatus | None
    to_status: SubmissionStatus
    comment: str | None
    created_at: datetime


class IndicatorResponse(BaseModel):
    status: str
    reason: str | None = None
    value: float | int | None = None
    unit: str
    provenance: dict[str, Any] | None = None


class SolarThermalResponse(BaseModel):
    """Solar water heater: thermal energy, kept apart from every electrical value."""

    metric_code: str
    value: float | int | None = None
    unit: str
    included_in_electricity: bool = False


class EnergySummaryResponse(BaseModel):
    """Backend-derived electrical indicators of an Energy submission.

    Renewable electricity is on-campus + procured only. Read-only: a wrong
    figure is corrected through the Manager's source values.
    """

    renewable_electricity_kwh: IndicatorResponse
    total_electricity_consumption_kwh: IndicatorResponse
    renewable_share_pct: IndicatorResponse
    estimated_avoided_grid_emissions_tco2e: IndicatorResponse
    solar_thermal: SolarThermalResponse
    provisional: bool


class GenericSubmissionResponse(BaseModel):
    id: UUID
    domain: OperationalDomain
    manager_user_id: UUID
    manager_display_name: str | None = None
    reporting_period_id: UUID
    reporting_period_label: str
    status: SubmissionStatus
    revision_number: int
    row_version: int
    remarks: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    correction_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    values: list[MetricValueResponse]
    review_actions: list[ReviewActionResponse] = []
    calculations: list[CalculationResponse] = []
    # Populated for waste submissions only; the authoritative dry and total
    # quantities always come from here, never from client arithmetic.
    waste: WasteSummaryResponse | None = None
    # Populated for energy submissions only: the authoritative electrical
    # indicators (renewable electricity excludes the solar water heater).
    energy: EnergySummaryResponse | None = None
