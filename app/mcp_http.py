"""Hosted MCP tools using the same authenticated customer OCR API."""

import base64
import binascii
from collections.abc import Mapping
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.deps import AsyncSessionLocal
from app.core.config import settings
from app.services.ocr_customers import customer_from_authorization

mcp = MCPServer("PageQuay OCR")


class CustomerMcpAuth:
    """Require an active customer key for every HTTP MCP message."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authorization = Headers(scope=scope).get("authorization", "")
        async with AsyncSessionLocal() as db:
            customer = await customer_from_authorization(db, authorization)
        if customer is None:
            await Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


def _authorization(ctx: Context[Any, Any]) -> str:
    headers: Mapping[str, str] = ctx.headers or {}
    authorization = headers.get("authorization", "")
    if not authorization:
        raise ValueError("Customer bearer key is required")
    return authorization


def _content(content_base64: str) -> bytes:
    if len(content_base64) > (settings.MAX_MCP_FILE_SIZE_BYTES * 4 // 3 + 8):
        raise ValueError("MCP file exceeds the configured size limit")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("content_base64 must be valid base64") from exc
    if len(content) > settings.MAX_MCP_FILE_SIZE_BYTES:
        raise ValueError("MCP file exceeds the configured size limit")
    return content


async def _api_request(
    method: str, path: str, authorization: str,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
) -> dict[str, Any]:
    # Route MCP calls through the customer API so authentication, limits, and
    # extraction behavior remain identical across transports.
    from app.main import application

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost", timeout=300) as client:
        response = await client.request(
            method, path, headers={"Authorization": authorization}, files=files
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


@mcp.tool()
async def extract_text(
    filename: str, mime_type: str, content_base64: str, ctx: Context[Any, Any]
) -> dict[str, Any]:
    """Extract text from an image, PDF, text file, or supported document."""
    return await _api_request(
        "POST", "/api/v1/ocr/extract", _authorization(ctx),
        [("file", (filename, _content(content_base64), mime_type))],
    )


@mcp.tool()
async def extract_bulk(
    files: list[dict[str, str]], ctx: Context[Any, Any]
) -> dict[str, Any]:
    """Extract text from up to the configured batch limit of base64 files."""
    if not files or len(files) > settings.MAX_OCR_BATCH_FILES:
        raise ValueError(f"Provide 1-{settings.MAX_OCR_BATCH_FILES} files")
    parts = [
        ("files", (item["filename"], _content(item["content_base64"]), item["mime_type"]))
        for item in files
    ]
    return await _api_request("POST", "/api/v1/ocr/bulk", _authorization(ctx), parts)


@mcp.tool()
async def get_ocr_usage(ctx: Context[Any, Any]) -> dict[str, Any]:
    """Get the customer's current month extraction usage and limit."""
    return await _api_request("GET", "/api/v1/ocr/usage", _authorization(ctx))


@mcp.tool()
async def get_capabilities(ctx: Context[Any, Any]) -> dict[str, Any]:
    """List supported extraction formats and configured limits."""
    return await _api_request("GET", "/api/v1/ocr/capabilities", _authorization(ctx))


def streamable_app() -> ASGIApp:
    hosts = [value.strip() for value in settings.MCP_ALLOWED_HOSTS.split(",") if value.strip()]
    origins = [value.strip() for value in settings.MCP_ALLOWED_ORIGINS.split(",") if value.strip()]
    security = TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)
    server = mcp.streamable_http_app(
        streamable_http_path="/", stateless_http=True, json_response=True,
        max_request_body_size=settings.MAX_MCP_FILE_SIZE_BYTES * 4 // 3 + 65536,
        transport_security=security,
    )
    return CustomerMcpAuth(server)
