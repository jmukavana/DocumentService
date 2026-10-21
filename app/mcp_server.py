"""MCP stdio bridge for customers of the OCR REST API.

Run with OCR_API_BASE_URL and OCR_API_TOKEN in the process environment.
"""

import base64
import binascii
import os

import httpx
from mcp.server import MCPServer

from app.core.config import settings

mcp = MCPServer("PageQuay OCR")


def _client_config() -> tuple[str, str]:
    url = os.environ.get("OCR_API_BASE_URL", "http://localhost:8000").rstrip("/")
    token = os.environ.get("OCR_API_TOKEN", "")
    if not token:
        raise ValueError("OCR_API_TOKEN is required")
    return url, token


def _decode(content_base64: str) -> bytes:
    if len(content_base64) > settings.MAX_MCP_FILE_SIZE_BYTES * 4 // 3 + 8:
        raise ValueError("MCP file exceeds the configured size limit")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("content_base64 must be valid base64") from exc
    if len(content) > settings.MAX_MCP_FILE_SIZE_BYTES:
        raise ValueError("MCP file exceeds the configured size limit")
    return content


@mcp.tool()
async def extract_text(filename: str, mime_type: str, content_base64: str) -> dict[str, object]:
    """Extract text from a base64-encoded image, PDF, text file, or document."""
    content = _decode(content_base64)
    url, token = _client_config()
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{url}/api/v1/ocr/extract",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, content, mime_type)},
        )
        response.raise_for_status()
        result: dict[str, object] = response.json()
        return result


@mcp.tool()
async def extract_bulk(files: list[dict[str, str]]) -> dict[str, object]:
    """Extract text from a batch of base64-encoded files."""
    if not files or len(files) > settings.MAX_OCR_BATCH_FILES:
        raise ValueError(f"Provide 1-{settings.MAX_OCR_BATCH_FILES} files")
    parts: list[tuple[str, tuple[str, bytes, str]]] = []
    for item in files:
        content = _decode(item["content_base64"])
        parts.append(("files", (item["filename"], content, item["mime_type"])))
    url, token = _client_config()
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{url}/api/v1/ocr/bulk",
            headers={"Authorization": f"Bearer {token}"},
            files=parts,
        )
        response.raise_for_status()
        result: dict[str, object] = response.json()
        return result


@mcp.tool()
async def get_ocr_usage() -> dict[str, object]:
    """Get this customer's current UTC month OCR requests and limit."""
    url, token = _client_config()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{url}/api/v1/ocr/usage", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result: dict[str, object] = response.json()
        return result


@mcp.tool()
async def get_capabilities() -> dict[str, object]:
    """List extractable formats and current file and batch limits."""
    url, token = _client_config()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{url}/api/v1/ocr/capabilities", headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result: dict[str, object] = response.json()
        return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
