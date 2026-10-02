from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
CertificateStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
TEXT_FIELDS = (
    "certificate_type", "title", "issuer", "registration_id", "authorization_no", "serial_no",
    "invoice_no", "manifest_doc_no", "quantity_unit", "notes",
)


def normalize_domain(value: str) -> str:
    domain = value.strip().casefold()
    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError("domain must be a lowercase identifier such as 'waste'")
    return domain


class CertificateUpdate(BaseModel):
    """Metadata edit. Only the fields sent are changed; the file is never replaced."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    domain: str | None = Field(default=None, max_length=40)
    certificate_type: str | None = Field(default=None, min_length=1, max_length=200)
    # Entered explicitly; never derived from certificate_date.
    reporting_year: int | None = Field(default=None, ge=2000, le=2100)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    issuer: str | None = Field(default=None, max_length=300)
    registration_id: str | None = Field(default=None, max_length=100)
    authorization_no: str | None = Field(default=None, max_length=100)
    serial_no: str | None = Field(default=None, max_length=100)
    certificate_date: date | None = None
    received_date: date | None = None
    invoice_no: str | None = Field(default=None, max_length=200)
    manifest_doc_no: str | None = Field(default=None, max_length=200)
    quantity_value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    quantity_unit: str | None = Field(default=None, max_length=20)
    display_order: int | None = Field(default=None, ge=0, le=100000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("domain")
    @classmethod
    def valid_domain(cls, value: str | None) -> str | None:
        return None if value is None else normalize_domain(value)


class AdminCertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: str
    certificate_type: str
    reporting_year: int
    title: str
    issuer: str | None
    registration_id: str | None
    authorization_no: str | None
    serial_no: str | None
    certificate_date: date | None
    received_date: date | None
    invoice_no: str | None
    manifest_doc_no: str | None
    quantity_value: Decimal | None
    quantity_unit: str | None
    original_filename: str
    mime_type: str
    byte_size: int
    sha256: str
    status: CertificateStatus
    display_order: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class PublicCertificate(BaseModel):
    """What the public may see: document metadata only - no storage key, path or uploader."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    certificate_type: str
    reporting_year: int
    issuer: str | None
    registration_id: str | None
    authorization_no: str | None
    serial_no: str | None
    received_date: date | None
    certificate_date: date | None
    invoice_no: str | None
    manifest_doc_no: str | None
    # Document metadata only. Never an input to any sustainability metric.
    quantity_value: float | None
    quantity_unit: str | None
    mime_type: str


class PublicCertificateList(BaseModel):
    domain: str
    reporting_year: int
    certificates: list[PublicCertificate]


class PublicCertificateYear(BaseModel):
    year: int
    certificate_count: int
    certificate_types: list[str]


class PublicCertificateYears(BaseModel):
    domain: str
    years: list[PublicCertificateYear]
