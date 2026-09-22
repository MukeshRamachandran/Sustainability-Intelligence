from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PublicationPeriod(BaseModel):
    id: UUID
    year: int
    month: int
    label: str


class DomainPublicationStatus(BaseModel):
    status: str
    submission_id: UUID | None = None
    revision_number: int | None = None


class PublicationBlocker(BaseModel):
    domain: str
    reason: Literal["missing_submission", "not_approved"]
    status: str


class PublicationReadinessResponse(BaseModel):
    reporting_period: PublicationPeriod
    required_domains: int
    approved_domains: int
    ready_to_publish: bool
    domains: dict[str, DomainPublicationStatus]
    blockers: list[PublicationBlocker]
