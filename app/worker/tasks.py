"""Background worker tasks: OCR and thumbnail generation.

Run the worker with:

    arq app.worker.settings.WorkerSettings
"""

from __future__ import annotations

import io
import csv
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pdf2image import convert_from_bytes, pdfinfo_from_bytes
from PIL import Image
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.deps import AsyncSessionLocal
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentStatus
from app.models.ocr_result import OcrResult
from app.services.compression import decompress
from app.services.storage import get_storage

logger = logging.getLogger("docservice.worker")

TESSERACT_CMD = shutil.which("tesseract")


def _run_tesseract(image: Image.Image, language: str) -> tuple[str, float]:
    """Run Tesseract once and return recognized lines and word confidence."""
    if TESSERACT_CMD is None:
        raise RuntimeError(
            "tesseract binary not found on PATH. Install tesseract-ocr to enable OCR."
        )

    # Save image to a temp PNG for tesseract.
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    # tesseract reads from stdin (image) and writes text to stdout.
    proc = subprocess.run(  # noqa: PLW1510
        [TESSERACT_CMD, "stdin", "stdout", "-l", language, "tsv"],
        input=buf.read(),
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed: {proc.stderr.decode(errors='replace')}")

    lines: list[str] = []
    words: list[str] = []
    scores: list[float] = []
    current_line: tuple[str, str, str, str] | None = None
    rows = csv.DictReader(io.StringIO(proc.stdout.decode(errors="replace")), delimiter="\t")
    for row in rows:
        word = (row.get("text") or "").strip()
        if not word:
            continue
        line = (row["page_num"], row["block_num"], row["par_num"], row["line_num"])
        if current_line is not None and line != current_line:
            lines.append(" ".join(words))
            words = []
        current_line = line
        words.append(word)
        score = float(row.get("conf") or -1)
        if score >= 0:
            scores.append(score / 100)
    if words:
        lines.append(" ".join(words))
    return "\n".join(lines), sum(scores) / len(scores) if scores else 0.0


@dataclass(frozen=True)
class OcrExtraction:
    text: str
    confidence: float
    page_count: int


def extract_ocr(data: bytes, mime_type: str, language: str) -> OcrExtraction:
    """Extract text from PDF pages or a single image."""
    if mime_type == "application/pdf":
        page_count = int(pdfinfo_from_bytes(data, timeout=30)["Pages"])
        if page_count < 1 or page_count > settings.MAX_OCR_PAGES:
            raise ValueError(f"PDF must have 1-{settings.MAX_OCR_PAGES} pages")
    else:
        with Image.open(io.BytesIO(data)) as source:
            page_count = getattr(source, "n_frames", 1)
        if page_count < 1 or page_count > settings.MAX_OCR_PAGES:
            raise ValueError(f"Image must have 1-{settings.MAX_OCR_PAGES} frames")

    all_text: list[str] = []
    confidences: list[float] = []
    for page in range(1, page_count + 1):
        if mime_type == "application/pdf":
            images = convert_from_bytes(
                data, dpi=200, first_page=page, last_page=page, thread_count=1, timeout=120,
            )
            if not images:
                raise ValueError(f"Could not render PDF page {page}")
            image = images[0]
        else:
            with Image.open(io.BytesIO(data)) as source:
                source.seek(page - 1)
                image = source.convert("RGB")
        try:
            text, confidence = _run_tesseract(image, language)
            all_text.append(text)
            confidences.append(confidence)
        finally:
            image.close()

    return OcrExtraction(
        text="\n\n--- Page Break ---\n\n".join(all_text),
        confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        page_count=page_count,
    )


async def ocr_task(
    ctx: dict[str, Any], document_id: str, version_id: str | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """OCR a document: decompress, convert PDF pages to images, run tesseract,
    store extracted text, update document status and full-text search vector."""
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return {"status": "error", "reason": "document_not_found"}
        if doc.status == DocumentStatus.deleted or (expected_sha256 and doc.sha256 != expected_sha256):
            return {"status": "skipped", "reason": "stale_or_deleted"}
        if doc.status == DocumentStatus.ocr_done:
            return {"status": "ocr_done", "document_id": document_id}

        # Mark OCR in progress.
        doc.status = DocumentStatus.ocr_pending
        await session.commit()

        try:
            storage = get_storage()
            raw = await storage.get(doc.stored_path)

            # Decompress if needed.
            from app.models.document import CompressionAlgo

            payload = decompress(raw, CompressionAlgo(doc.compression_algo))

            extraction = await run_in_threadpool(extract_ocr, payload, doc.mime_type,
                                                 settings.OCR_LANGUAGE)
            extracted_text = extraction.text
            avg_confidence = extraction.confidence

            # Build denormalized search text: filename + OCR content.
            search_text = f"{doc.filename}\n\n{extracted_text}".strip()

            # A newer version may have arrived while OCR was running.
            current = await session.scalar(
                select(Document).where(Document.id == doc.id).with_for_update()
                .execution_options(populate_existing=True)
            )
            if current is None or current.status == DocumentStatus.deleted or (
                expected_sha256 and current.sha256 != expected_sha256
            ):
                await session.rollback()
                return {"status": "skipped", "reason": "stale_or_deleted"}
            if current.status == DocumentStatus.ocr_done:
                await session.rollback()
                return {"status": "ocr_done", "document_id": document_id}

            # Persist OCR result.
            ocr = OcrResult(
                document_id=doc.id,
                version_id=UUID(version_id) if version_id else None,
                extracted_text=extracted_text,
                language=settings.OCR_LANGUAGE,
                confidence=avg_confidence,
            )
            session.add(ocr)

            # Update document with OCR text for full-text search.
            current.status = DocumentStatus.ocr_done
            current.search_text = search_text
            session.add(AuditLog(
                actor_id="system", action="ocr_complete", document_id=doc.id,
                details={"version_id": version_id, "characters": len(extracted_text)},
            ))
            await session.commit()

            return {
                "status": "ocr_done",
                "document_id": document_id,
                "characters": len(extracted_text),
                "confidence": round(avg_confidence, 4),
            }

        except Exception as exc:
            logger.exception("OCR failed for document %s", document_id)
            await session.rollback()
            doc = await session.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
                .execution_options(populate_existing=True)
            )
            if doc is None:
                return {"status": "error", "reason": "document_not_found"}
            if doc.status == DocumentStatus.deleted or (expected_sha256 and doc.sha256 != expected_sha256):
                await session.rollback()
                return {"status": "skipped", "reason": "stale_or_deleted"}
            doc.status = DocumentStatus.ocr_failed
            session.add(AuditLog(
                actor_id="system", action="ocr_failed", document_id=doc.id,
                details={"version_id": version_id, "error": str(exc)},
            ))
            await session.commit()
            return {"status": "ocr_failed", "document_id": document_id, "error": str(exc)}


async def thumbnail_task(ctx: dict[str, Any], document_id: str) -> dict[str, Any]:
    """Generate a small JPEG thumbnail for image/PDF documents."""
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return {"status": "error", "reason": "document_not_found"}

        try:
            storage = get_storage()
            raw = await storage.get(doc.stored_path)
            from app.models.document import CompressionAlgo

            payload = decompress(raw, CompressionAlgo(doc.compression_algo))

            if doc.mime_type == "application/pdf":
                images = convert_from_bytes(payload, dpi=72, first_page=1, last_page=1)
                img = images[0] if images else None
            else:
                img = Image.open(io.BytesIO(payload)).convert("RGB")

            if img is None:
                return {"status": "skipped", "reason": "no_renderable_content"}

            img.thumbnail((256, 256))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=80)
            thumb_bytes = out.getvalue()

            thumb_key = f"thumbs/{document_id}.jpg"
            await storage.save(thumb_key, thumb_bytes)
            return {"status": "thumbnail_done", "document_id": document_id}

        except Exception as exc:
            logger.exception("Thumbnail failed for document %s", document_id)
            return {"status": "thumbnail_failed", "document_id": document_id, "error": str(exc)}
