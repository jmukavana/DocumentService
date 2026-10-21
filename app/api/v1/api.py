"""API v1 router aggregation."""

from fastapi import APIRouter, Depends

from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.ocr_service import admin_router as ocr_admin_router
from app.api.v1.ocr_service import router as ocr_router
from app.core.auth import require_api_key

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(ocr_router, prefix="/ocr", tags=["customer OCR"])
api_router.include_router(ocr_admin_router, prefix="/ocr/admin", tags=["OCR administration"])
api_router.include_router(
    documents_router, prefix="/documents", tags=["documents"],
    dependencies=[Depends(require_api_key)],
)
