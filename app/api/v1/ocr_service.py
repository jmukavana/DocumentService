"""Customer OCR product and administrator provisioning API."""

import logging
import zipfile
from datetime import UTC, datetime
from uuid import UUID
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db
from app.core.auth import require_api_key
from app.core.config import settings
from app.core.security import sanitize_filename
from app.models.customer import Customer, CustomerApiKey, OcrUsage
from app.schemas.document import DirectOcrResponse
from app.schemas.ocr_customer import (
    BulkExtractItem,
    BulkExtractResponse,
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    ExtractedContentResponse,
    KeyCreate,
    KeyIssued,
    UsageResponse,
)
from app.services.extraction import (
    IMAGE_EXTENSIONS,
    OFFICE_EXTENSIONS,
    TEXT_EXTENSIONS,
    UnsupportedExtractionFormat,
    detect_mime_type,
    extract_content,
)
from app.services.ocr_customers import (
    create_key,
    current_period,
    refund_request,
    require_customer,
    reserve_request,
)

router = APIRouter()
admin_router = APIRouter(dependencies=[Depends(require_api_key)])
logger = logging.getLogger("docservice.ocr_service")


async def _extract_one(
    file: UploadFile, customer: Customer, db: AsyncSession
) -> ExtractedContentResponse:
    data = await file.read(settings.MAX_FILE_SIZE_BYTES + 1)
    if len(data) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, "File exceeds maximum allowed size")
    mime_type = detect_mime_type(data, file.filename or "unnamed", file.content_type)

    period = await reserve_request(db, customer)
    try:
        result = await run_in_threadpool(
            extract_content, data, file.filename or "unnamed", mime_type, settings.OCR_LANGUAGE
        )
    except UnsupportedExtractionFormat as exc:
        await refund_request(db, customer, period)
        raise HTTPException(415, str(exc)) from exc
    except (UnidentifiedImageError, Image.DecompressionBombError, PDFPageCountError,
            PDFSyntaxError, zipfile.BadZipFile, ElementTree.ParseError, ValueError,
            KeyError, IndexError) as exc:
        await refund_request(db, customer, period)
        raise HTTPException(422, "File could not be read for extraction") from exc
    except (PDFInfoNotInstalledError, RuntimeError, OSError) as exc:
        await refund_request(db, customer, period)
        logger.exception("Customer OCR failed")
        raise HTTPException(503, "OCR engine unavailable") from exc
    except Exception:
        await refund_request(db, customer, period)
        logger.exception("Unexpected customer OCR failure")
        raise

    return ExtractedContentResponse(
        filename=sanitize_filename(file.filename or "unnamed"),
        extracted_text=result.text,
        language=settings.OCR_LANGUAGE,
        confidence=result.confidence,
        page_count=result.page_count,
        extraction_method=result.method,
    )


@router.post("/extract", response_model=ExtractedContentResponse)
async def extract_for_customer(
    file: UploadFile = File(...),
    customer: Customer = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> ExtractedContentResponse:
    return await _extract_one(file, customer, db)


@router.post("/bulk", response_model=BulkExtractResponse)
async def extract_bulk_for_customer(
    files: list[UploadFile] = File(...),
    customer: Customer = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> BulkExtractResponse:
    if len(files) > settings.MAX_OCR_BATCH_FILES:
        raise HTTPException(413, f"Batch exceeds {settings.MAX_OCR_BATCH_FILES} files")
    items: list[BulkExtractItem] = []
    accepted = failed = 0
    for file in files:
        try:
            result = await _extract_one(file, customer, db)
            items.append(BulkExtractItem(filename=result.filename, status="accepted", result=result))
            accepted += 1
        except HTTPException as exc:
            await db.rollback()
            items.append(BulkExtractItem(filename=sanitize_filename(file.filename or "unnamed"),
                                         status="failed", error=str(exc.detail)))
            failed += 1
    return BulkExtractResponse(items=items, accepted=accepted, failed=failed)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    customer: Customer = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    period = current_period()
    usage = await db.get(OcrUsage, (customer.id, period))
    return UsageResponse(customer_id=customer.id, period=period,
                         requests=usage.requests if usage else 0,
                         monthly_request_limit=customer.monthly_request_limit)


@router.get("/capabilities")
async def get_capabilities(customer: Customer = Depends(require_customer)) -> dict[str, object]:
    return {
        "storage_accepts_any_file_type": True,
        "ocr_extensions": sorted(IMAGE_EXTENSIONS | {".pdf"}),
        "embedded_text_extensions": sorted(TEXT_EXTENSIONS | OFFICE_EXTENSIONS | {".eml"}),
        "max_file_size_bytes": settings.MAX_FILE_SIZE_BYTES,
        "max_mcp_file_size_bytes": settings.MAX_MCP_FILE_SIZE_BYTES,
        "max_ocr_pages": settings.MAX_OCR_PAGES,
        "max_bulk_files": settings.MAX_OCR_BATCH_FILES,
    }


@admin_router.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(
    body: CustomerCreate, db: AsyncSession = Depends(get_db)
) -> CustomerResponse:
    customer = Customer(name=body.name, email=body.email.lower(),
                        monthly_request_limit=body.monthly_request_limit, active=True)
    db.add(customer)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Customer email already exists") from exc
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer, from_attributes=True)


@admin_router.post("/customers/{customer_id}/keys", response_model=KeyIssued, status_code=201)
async def issue_key(
    customer_id: UUID, body: KeyCreate, db: AsyncSession = Depends(get_db)
) -> KeyIssued:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    key, token = create_key(customer_id, body.name)
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return KeyIssued(id=key.id, name=key.name, key_prefix=key.key_prefix, token=token)


@admin_router.patch("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID, body: CustomerUpdate, db: AsyncSession = Depends(get_db)
) -> CustomerResponse:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    if body.monthly_request_limit is not None:
        customer.monthly_request_limit = body.monthly_request_limit
    if body.active is not None:
        customer.active = body.active
    await db.commit()
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer, from_attributes=True)


@admin_router.delete("/customers/{customer_id}/keys/{key_id}", status_code=204)
async def revoke_key(
    customer_id: UUID, key_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    key = await db.scalar(select(CustomerApiKey).where(
        CustomerApiKey.id == key_id, CustomerApiKey.customer_id == customer_id
    ))
    if key is None:
        raise HTTPException(404, "API key not found")
    key.revoked_at = datetime.now(UTC)
    await db.commit()


@admin_router.get("/customers/{customer_id}/usage", response_model=UsageResponse)
async def get_customer_usage(
    customer_id: UUID, db: AsyncSession = Depends(get_db)
) -> UsageResponse:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    period = current_period()
    usage = await db.get(OcrUsage, (customer.id, period))
    return UsageResponse(customer_id=customer.id, period=period,
                         requests=usage.requests if usage else 0,
                         monthly_request_limit=customer.monthly_request_limit)
