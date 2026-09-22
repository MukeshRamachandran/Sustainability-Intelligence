from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class EvidenceResponse(BaseModel):
    id: UUID
    submission_id: UUID
    metric_code: str | None
    evidence_category: str | None
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    uploaded_at: datetime
    committed_at: datetime | None
    lifecycle_state: Literal["temporary", "committed"]
    revision_number: int
    is_current: bool
    superseded_at: datetime | None
    replaced_by_evidence_id: UUID | None
    removed_at: datetime | None


class EvidenceRepositoryPeriod(BaseModel):
    id: UUID
    year: int
    month: int


class EvidenceRepositoryUploader(BaseModel):
    id: UUID
    display_name: str


class EvidenceRepositoryItem(BaseModel):
    evidence_id: UUID
    submission_id: UUID
    domain: str
    reporting_period: EvidenceRepositoryPeriod
    submission_status: str
    revision_number: int
    is_latest_revision: bool
    metric_code: str | None
    metric_display_name: str | None
    evidence_category: str | None
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    uploaded_at: datetime
    committed_at: datetime
    uploaded_by: EvidenceRepositoryUploader


class EvidenceRepositoryResponse(BaseModel):
    items: list[EvidenceRepositoryItem]
    page: int
    page_size: int
    total_items: int
    total_pages: int
