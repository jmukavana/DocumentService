"""Tests for document CRUD, upload, download, versions, delete."""

import asyncio
import io
import uuid

from httpx import ASGITransport, AsyncClient

from app.api.deps import AsyncSessionLocal, engine
from tests.conftest import cleanup_app, make_app_with_session, truncate_tables


def _run_with_client(test_fn):
    """Helper: create session+app+client, run test_fn (sync), cleanup."""

    async def _inner():
        await engine.dispose()
        async with AsyncSessionLocal() as session:
            app = make_app_with_session(session)
            transport = ASGITransport(app=app)
            ac = AsyncClient(transport=transport, base_url="http://testserver",
                             auth=("test-key", "test-secret"))
            await ac.__aenter__()
            try:
                await test_fn(ac)
            finally:
                await ac.__aexit__(None, None, None)
                cleanup_app(app)
                await truncate_tables(session)
        await engine.dispose()

    asyncio.run(_inner())


def test_upload_document(prepare_database):
    """Upload a single document returns 201 and metadata."""

    async def test(ac):
        files = {"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")}
        resp = await ac.post("/api/v1/documents/upload", files=files)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["filename"] == "hello.txt"
        assert data["mime_type"] == "text/plain"
        assert data["size_bytes"] == 11
        assert data["status"] == "ready"
        assert "id" in data
        assert "sha256" in data

    _run_with_client(test)


def test_upload_exceeds_size_limit(prepare_database, monkeypatch):
    """Upload larger than MAX_FILE_SIZE_BYTES returns 413."""
    from app.core import config
    monkeypatch.setattr(config.settings, "MAX_FILE_SIZE_BYTES", 5)

    async def test(ac):
        files = {"file": ("big.txt", io.BytesIO(b"this is too long"), "text/plain")}
        resp = await ac.post("/api/v1/documents/upload", files=files)
        assert resp.status_code == 413, resp.text

    _run_with_client(test)


def test_upload_duplicate_is_deduplicated(prepare_database):
    """Uploading identical content twice returns the same document (dedup)."""

    async def test(ac):
        files = {"file": ("dup.txt", io.BytesIO(b"duplicate content"), "text/plain")}
        r1 = await ac.post("/api/v1/documents/upload", files=files)
        assert r1.status_code == 201
        id1 = r1.json()["id"]

        r2 = await ac.post("/api/v1/documents/upload", files=files)
        assert r2.status_code == 201
        id2 = r2.json()["id"]
        assert id1 == id2

    _run_with_client(test)


def test_list_documents(prepare_database):
    """List endpoint returns paginated results."""

    async def test(ac):
        await ac.post("/api/v1/documents/upload", files={"file": ("a.txt", io.BytesIO(b"aaa"), "text/plain")})
        await ac.post("/api/v1/documents/upload", files={"file": ("b.txt", io.BytesIO(b"bbb"), "text/plain")})

        resp = await ac.get("/api/v1/documents/")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    _run_with_client(test)


def test_get_document(prepare_database):
    """Get a single document by ID."""

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("getme.txt", io.BytesIO(b"content"), "text/plain")},
        )
        doc_id = upload.json()["id"]

        resp = await ac.get(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == doc_id
        assert data["filename"] == "getme.txt"

    _run_with_client(test)


def test_get_nonexistent_document(prepare_database):
    """Get a document that doesn't exist returns 404."""

    async def test(ac):
        resp = await ac.get(f"/api/v1/documents/{uuid.uuid4()}")
        assert resp.status_code == 404, resp.text

    _run_with_client(test)


def test_download_document(prepare_database):
    """Download returns the stored file content."""

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("download.txt", io.BytesIO(b"download me"), "text/plain")},
        )
        doc_id = upload.json()["id"]

        resp = await ac.get(f"/api/v1/documents/{doc_id}/download")
        assert resp.status_code == 200, resp.text
        assert resp.content == b"download me"

    _run_with_client(test)


def test_update_document_metadata(prepare_database):
    """Update filename and department."""

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("old.txt", io.BytesIO(b"x"), "text/plain")},
        )
        doc_id = upload.json()["id"]

        resp = await ac.put(
            f"/api/v1/documents/{doc_id}",
            json={"filename": "new.txt", "department_id": "finance"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["filename"] == "new.txt"
        assert data["department_id"] == "finance"

    _run_with_client(test)


def test_delete_document(prepare_database):
    """Soft-delete returns 204, subsequent GET returns 404."""

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("todelete.txt", io.BytesIO(b"x"), "text/plain")},
        )
        doc_id = upload.json()["id"]

        resp = await ac.delete(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 204, resp.text

        resp = await ac.get(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 404, resp.text

    _run_with_client(test)


def test_upload_version(prepare_database):
    """Upload a new version increments version_no."""

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("v1.txt", io.BytesIO(b"version one"), "text/plain")},
        )
        doc_id = upload.json()["id"]

        resp = await ac.post(
            f"/api/v1/documents/{doc_id}/versions",
            files={"file": ("v2.txt", io.BytesIO(b"version two"), "text/plain")},
            data={"change_note": "second version"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["version_no"] == 1
        assert data["size_bytes"] == 11

    _run_with_client(test)


def test_list_versions(prepare_database):
    """List versions returns version history."""

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("base.txt", io.BytesIO(b"base"), "text/plain")},
        )
        doc_id = upload.json()["id"]

        await ac.post(
            f"/api/v1/documents/{doc_id}/versions",
            files={"file": ("v.txt", io.BytesIO(b"v"), "text/plain")},
            data={"change_note": "note"},
        )

        resp = await ac.get(f"/api/v1/documents/{doc_id}/versions")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        assert data[0]["change_note"] == "note"

    _run_with_client(test)


def test_bulk_upload_mixed(prepare_database):
    """Bulk upload accepts valid files, skips duplicates, rejects bad ones."""

    async def test(ac):
        files = [
            ("files", ("ok1.txt", io.BytesIO(b"ok one"), "text/plain")),
            ("files", ("ok2.txt", io.BytesIO(b"ok two"), "text/plain")),
        ]
        resp = await ac.post("/api/v1/documents/bulk-upload", files=files)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["accepted"] == 2
        assert data["skipped"] == 0
        assert data["failed"] == 0

        resp = await ac.post(
            "/api/v1/documents/bulk-upload",
            files=[("files", ("ok1.txt", io.BytesIO(b"ok one"), "text/plain"))],
        )
        data = resp.json()
        assert data["skipped"] == 1
        assert data["accepted"] == 0

    _run_with_client(test)


def test_unsupported_media_type(prepare_database):
    """Unsupported mime type returns 415."""

    async def test(ac):
        files = {"file": ("script.sh", io.BytesIO(b"echo hi"), "application/x-shellscript")}
        resp = await ac.post("/api/v1/documents/upload", files=files)
        assert resp.status_code == 415, resp.text

    _run_with_client(test)


def test_pdf_download_round_trip_and_audit(prepare_database):
    """Compressed PDF downloads retain their bytes and write audit entries."""
    async def test(ac):
        original = b"%PDF-1.4\n" + b"repeated payload " * 200
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("sample.pdf", io.BytesIO(original), "application/pdf")},
        )
        assert upload.status_code == 201, upload.text
        doc_id = upload.json()["id"]
        download = await ac.get(f"/api/v1/documents/{doc_id}/download")
        assert download.status_code == 200
        assert download.content == original
        assert "content-encoding" not in download.headers
        assert "filename*=UTF-8''sample.pdf" in download.headers["content-disposition"]

        audit = await ac.get(f"/api/v1/documents/admin/audit-logs?document_id={doc_id}")
        assert audit.status_code == 200, audit.text
        assert {item["action"] for item in audit.json()["items"]} == {"upload", "download"}
        assert all(item["actor_id"] == "test-key" for item in audit.json()["items"])

    _run_with_client(test)


def test_image_ocr_worker_writes_audit(prepare_database, monkeypatch):
    """An OCR completion records extracted text and a system audit event."""
    from PIL import Image

    from app.worker import tasks

    monkeypatch.setattr(tasks, "_run_tesseract", lambda image, language: ("sample text", 0.9))
    image = io.BytesIO()
    Image.new("RGB", (4, 4), color="white").save(image, format="PNG")

    async def test(ac):
        upload = await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("scan.png", io.BytesIO(image.getvalue()), "image/png")},
        )
        assert upload.status_code == 201, upload.text
        doc_id = upload.json()["id"]
        result = await tasks.ocr_task({}, doc_id)
        assert result["status"] == "ocr_done"
        assert result["characters"] == len("sample text")

        audit = await ac.get(f"/api/v1/documents/admin/audit-logs?document_id={doc_id}")
        events = {(item["action"], item["actor_id"]) for item in audit.json()["items"]}
        assert ("ocr_complete", "system") in events

    _run_with_client(test)


def test_direct_ocr_upload_returns_text_without_document(prepare_database, monkeypatch):
    """Direct OCR returns text without creating a stored document."""
    from PIL import Image

    from app.worker import tasks

    monkeypatch.setattr(tasks, "_run_tesseract", lambda image, language: ("invoice 123", 0.85))
    image = io.BytesIO()
    Image.new("RGB", (4, 4), color="white").save(image, format="PNG")

    async def test(ac):
        response = await ac.post(
            "/api/v1/documents/ocr/upload",
            files={"file": ("invoice.png", io.BytesIO(image.getvalue()), "image/png")},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "filename": "invoice.png",
            "extracted_text": "invoice 123",
            "language": "eng",
            "confidence": 0.85,
            "page_count": 1,
        }

        documents = await ac.get("/api/v1/documents/")
        assert documents.json()["total"] == 0
        audit = await ac.get("/api/v1/documents/admin/audit-logs?action=ocr_direct")
        assert audit.json()["total"] == 1
        assert audit.json()["items"][0]["document_id"] is None

    _run_with_client(test)


def test_direct_ocr_rejects_non_image(prepare_database):
    async def test(ac):
        response = await ac.post(
            "/api/v1/documents/ocr/upload",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 415

    _run_with_client(test)
