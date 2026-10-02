from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.models.enums import LEGACY_FACTOR_CODES, FactorCode, FactorSetStatus


class FactorWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: FactorCode
    factor_value: Decimal = Field(max_digits=20, decimal_places=10, ge=0)
    activity_unit: str = Field(min_length=1, max_length=40)
    result_unit: str = Field(default="kgCO2e", min_length=1, max_length=40)
    source_reference: str | None = Field(default=None, max_length=2000)
    source_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("factor_value")
    @classmethod
    def finite_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("factor value must be finite")
        return value

    @field_validator("code")
    @classmethod
    def governed_code(cls, value: FactorCode) -> FactorCode:
        if value in LEGACY_FACTOR_CODES:
            raise ValueError("the litre-based LPG factor is retired; use LPG_KG (kgCO2e/kg)")
        return value


class FactorSetWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: str = Field(min_length=1, max_length=100)
    effective_from: date
    source_note: str = Field(min_length=1, max_length=4000)
    factors: list[FactorWrite]

    @model_validator(mode="after")
    def unique_factors(self) -> "FactorSetWrite":
        codes = [item.code for item in self.factors]
        if len(codes) != len(set(codes)):
            raise ValueError("factor codes must be unique")
        return self


class FactorSetCreate(FactorSetWrite):
    pass


class FactorSetUpdate(FactorSetWrite):
    expected_row_version: int = Field(ge=1)


class FactorResponse(BaseModel):
    id: UUID
    code: FactorCode
    factor_value: Decimal
    activity_unit: str
    result_unit: str
    source_reference: str | None
    source_url: str | None
    notes: str | None


class FactorSetResponse(BaseModel):
    id: UUID
    version: str
    status: FactorSetStatus
    effective_from: date | None
    source_note: str
    created_by: UUID | None
    created_by_name: str | None
    activated_by: UUID | None
    activated_by_name: str | None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    row_version: int
    factors: list[FactorResponse]


class CalculationResponse(BaseModel):
    status: str
    reason: str | None = None
    calculation_code: str
    activity_metric_code: str | None = None
    activity_value: Decimal | None = None
    activity_unit: str | None = None
    factor_set_id: UUID | None = None
    factor_set_version: str | None = None
    factor_code: FactorCode | None = None
    factor_value: Decimal | None = None
    factor_unit: str | None = None
    result_kgco2e: Decimal | None = None
    result_value: Decimal | None = None
    result_unit: str | None = None
    formula_version: str | None = None
    provisional: bool = False
    # Present only when the activity behind the result is derived from another
    # source value (kWh-based DG): source kWh, governed SFC and derived litres.
    derivation: dict[str, Any] | None = None
