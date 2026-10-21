"""Customer provisioning, authentication, usage, and quota behavior."""

import asyncio
import io

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps import AsyncSessionLocal, engine
from app.main import create_app
from tests.conftest import truncate_tables


def test_customer_ocr_lifecycle(prepare_database, monkeypatch):
    from app.worker import tasks

    monkeypatch.setattr(tasks, "_run_tesseract", lambda image, language: ("invoice 123", 0.85))
    image = io.BytesIO()
    Image.new("RGB", (4, 4), color="white").save(image, format="PNG")

    async def check() -> None:
        await engine.dispose()
        async with AsyncSessionLocal() as session:
            await truncate_tables(session)
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            path = "/api/v1/ocr"
            assert (await client.get(f"{path}/usage")).status_code == 401
            customer = await client.post(
                f"{path}/admin/customers", auth=("test-key", "test-secret"),
                json={"name": "Acme", "email": "acme@example.com", "monthly_request_limit": 1},
            )
            assert customer.status_code == 201, customer.text
            customer_id = customer.json()["id"]
            key = await client.post(
                f"{path}/admin/customers/{customer_id}/keys",
                auth=("test-key", "test-secret"), json={"name": "production"},
            )
            assert key.status_code == 201, key.text
            token = key.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            assert (await client.get(f"{path}/usage", headers=headers)).json()["requests"] == 0

            bad = await client.post(f"{path}/extract", headers=headers,
                                    files={"file": ("bad.png", b"bad", "image/png")})
            assert bad.status_code == 422
            assert (await client.get(f"{path}/usage", headers=headers)).json()["requests"] == 0

            result = await client.post(
                f"{path}/extract", headers=headers,
                files={"file": ("invoice.png", image.getvalue(), "image/png")},
            )
            assert result.status_code == 200, result.text
            assert result.json()["extracted_text"] == "invoice 123"
            assert (await client.get(f"{path}/usage", headers=headers)).json()["requests"] == 1
            limited = await client.post(
                f"{path}/extract", headers=headers,
                files={"file": ("invoice.png", image.getvalue(), "image/png")},
            )
            assert limited.status_code == 429
            disabled = await client.patch(
                f"{path}/admin/customers/{customer_id}",
                auth=("test-key", "test-secret"), json={"active": False},
            )
            assert disabled.status_code == 200
            assert (await client.get(f"{path}/usage", headers=headers)).status_code == 401
            revoked = await client.delete(
                f"{path}/admin/customers/{customer_id}/keys/{key.json()['id']}",
                auth=("test-key", "test-secret"),
            )
            assert revoked.status_code == 204
            assert (await client.get(f"{path}/usage", headers=headers)).status_code == 401
        await engine.dispose()

    asyncio.run(check())
