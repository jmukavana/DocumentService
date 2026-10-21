"""Authentication checks that do not require a database."""

import asyncio

from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import create_app


def test_document_routes_require_basic_auth():
    async def check():
        async with AsyncClient(transport=ASGITransport(app=create_app()),
                               base_url="http://testserver") as client:
            path = "/api/v1/documents/not-a-uuid"
            missing = await client.get(path)
            wrong = await client.get(path, auth=("test-key", "wrong"))
            valid = await client.get(path, auth=("test-key", "test-secret"))
            health = await client.get("/api/v1/health")
            assert missing.status_code == 401
            assert missing.headers["www-authenticate"] == "Basic"
            assert wrong.status_code == 401
            assert valid.status_code == 422
            assert health.status_code == 200

    asyncio.run(check())


def test_unconfigured_credentials_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", None)

    async def check():
        async with AsyncClient(transport=ASGITransport(app=create_app()),
                               base_url="http://testserver") as client:
            response = await client.get("/api/v1/documents/not-a-uuid",
                                        auth=("test-key", "test-secret"))
            assert response.status_code == 503

    asyncio.run(check())
