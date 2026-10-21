"""Tests for full-text search."""

import asyncio
import io

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text

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
                await test_fn(ac, session)
            finally:
                await ac.__aexit__(None, None, None)
                cleanup_app(app)
                await truncate_tables(session)
        await engine.dispose()

    asyncio.run(_inner())


def test_search_endpoint_returns_matching_documents(prepare_database):
    """Full-text search finds documents matching the query."""

    async def test(ac, session):
        await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("report.txt", io.BytesIO(b"quarterly earnings report 2026"), "text/plain")},
        )
        await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", io.BytesIO(b"meeting notes about lunch"), "text/plain")},
        )

        await session.execute(
            sa_text("UPDATE documents SET search_text = 'quarterly earnings report 2026' WHERE filename = 'report.txt'")
        )
        await session.execute(
            sa_text("UPDATE documents SET search_text = 'meeting notes about lunch' WHERE filename = 'notes.txt'")
        )
        await session.commit()

        resp = await ac.get("/api/v1/documents/search?q=earnings")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["filename"] == "report.txt"

        resp = await ac.get("/api/v1/documents/search?q=lunch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["filename"] == "notes.txt"

    _run_with_client(test)


def test_search_no_query_returns_empty(prepare_database):
    """Search endpoint requires q parameter."""

    async def test(ac, session):
        resp = await ac.get("/api/v1/documents/search")
        assert resp.status_code == 422, resp.text

    _run_with_client(test)


def test_search_nonexistent_returns_empty(prepare_database):
    """Search for a term not in any document returns 0 results."""

    async def test(ac, session):
        resp = await ac.get("/api/v1/documents/search?q=zzzzyyyyxyz")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    _run_with_client(test)


def test_list_search_param(prepare_database):
    """List endpoint search parameter uses full-text search."""

    async def test(ac, session):
        await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("alpha.txt", io.BytesIO(b"alpha project documents"), "text/plain")},
        )
        await ac.post(
            "/api/v1/documents/upload",
            files={"file": ("beta.txt", io.BytesIO(b"beta project files"), "text/plain")},
        )

        await session.execute(
            sa_text("UPDATE documents SET search_text = 'alpha project documents' WHERE filename = 'alpha.txt'")
        )
        await session.execute(
            sa_text("UPDATE documents SET search_text = 'beta project files' WHERE filename = 'beta.txt'")
        )
        await session.commit()

        resp = await ac.get("/api/v1/documents/?search=alpha")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["filename"] == "alpha.txt"

    _run_with_client(test)
