"""Public and administrator OCR customer schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.document import DirectOcrResponse


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    monthly_request_limit: int = Field(ge=0)


class CustomerResponse(BaseModel):
    id: UUID
    name: str
    email: str
    monthly_request_limit: int
    active: bool


class CustomerUpdate(BaseModel):
    monthly_request_limit: int | None = Field(default=None, ge=0)
    active: bool | None = None


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class KeyIssued(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    token: str


class UsageResponse(BaseModel):
    customer_id: UUID
    period: str
    requests: int
    monthly_request_limit: int


class ExtractedContentResponse(DirectOcrResponse):
    extraction_method: str


class BulkExtractItem(BaseModel):
    filename: str
    status: str
    result: ExtractedContentResponse | None = None
    error: str | None = None


class BulkExtractResponse(BaseModel):
    items: list[BulkExtractItem]
    accepted: int
    failed: int
