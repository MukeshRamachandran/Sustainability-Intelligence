from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WasteItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material_code: str = Field(min_length=1, max_length=60)
    # gt=0: a real material row always carries a positive quantity. An absent
    # material is expressed by omitting the row, never by a zero row.
    quantity_kg: Decimal = Field(max_digits=20, decimal_places=6, gt=0)

    @field_validator("quantity_kg")
    @classmethod
    def finite_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("waste quantities must be finite")
        return value


class WasteItemResponse(BaseModel):
    material_code: str
    material_display_name: str
    category_code: str
    category_display_name: str
    quantity_kg: Decimal


class WasteCatalogCategory(BaseModel):
    code: str
    display_name: str
    sort_order: int | None = None
    quantity_kg: Decimal | None = None


class WasteCatalogMaterial(BaseModel):
    code: str
    display_name: str
    category_code: str
    sort_order: int | None = None


class WasteCatalogResponse(BaseModel):
    categories: list[WasteCatalogCategory]
    materials: list[WasteCatalogMaterial]


class WasteSummaryResponse(BaseModel):
    wet_waste_generated_kg: Decimal
    dry_waste_generated_kg: Decimal
    total_waste_generated_kg: Decimal
    # Calculated by the backend, never entered: diverted from landfill = dry
    # waste; per person = total / the year's governed population (None when no
    # population reference exists for the reporting year).
    waste_diverted_from_landfill_kg: Decimal
    waste_per_capita_kg: Decimal | None = None
    items: list[WasteItemResponse]
    categories: list[WasteCatalogCategory]
