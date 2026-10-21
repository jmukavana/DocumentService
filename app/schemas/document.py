"""Pydantic request/response schemas for documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.document import CompressionAlgo, DocumentStatus


class DocumentBase(BaseModel):
    filename: str = Field(..., max_length=512)
    mime_type: str = Field(..., max_length=128)
    size_bytes: int = Field(..., ge=0)
    owner_id: str | None = Field(default=None, max_length=256)
    department_id: str | None = Field(default=None, max_length=256)


class DocumentCreate(DocumentBase):
    stored_path: str
    sha256: str = Field(..., min_length=64, max_length=64)
    compression_algo: CompressionAlgo = CompressionAlgo.none
    original_size_bytes: int | None = Field(default=None, ge=0)
    compressed_size_bytes: int | None = Field(default=None, ge=0)
    compression_ratio: float | None = Field(default=None, ge=0, le=1)
    status: DocumentStatus = DocumentStatus.ready


class DocumentUpdate(BaseModel):
    filename: str | None = Field(default=None, max_length=512)
    owner_id: str | None = Field(default=None, max_length=256)
    department_id: str | None = Field(default=None, max_length=256)


class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stored_path: str
    sha256: str
    compression_algo: CompressionAlgo
    original_size_bytes: int | None = None
    compressed_size_bytes: int | None = None
    compression_ratio: float | None = None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_no: int
    size_bytes: int
    uploaded_by: str | None = None
    change_note: str | None = None
    created_at: datetime


class OcrResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    extracted_text: str | None = None
    language: str
    confidence: float | None = None
    processed_at: datetime | None = None


class DirectOcrResponse(BaseModel):
    filename: str
    extracted_text: str
    language: str
    confidence: float
    page_count: int


class OcrTriggerResponse(BaseModel):
    document_id: UUID
    status: str  # queued, already_done, already_failed, not_eligible
    job_id: str | None = None


class BulkUploadItem(BaseModel):
    filename: str
    status: str  # accepted, skipped_duplicate, failed
    document_id: UUID | None = None
    error: str | None = None
    document_status: DocumentStatus | None = None


class BulkUploadResponse(BaseModel):
    items: list[BulkUploadItem]
    accepted: int
    skipped: int
    failed: int


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: str | None = None
    action: str
    document_id: UUID | None = None
    details: dict[str, Any] | None = None
    ip: str | None = None
    created_at: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def stringify_ip(cls, value: Any) -> str | None:
        return str(value) if value is not None else None


class AuditLogList(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
