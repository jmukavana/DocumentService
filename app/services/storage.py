"""Storage service — pluggable backend abstraction.

Default backend is local filesystem. Switch to S3/MinIO via
STORAGE_BACKEND=s3 in the environment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import boto3  # type: ignore[import-untyped]
from botocore.client import BaseClient  # type: ignore[import-untyped]

from app.core.config import settings


@dataclass(frozen=True)
class StoredFile:
    path: str
    size_bytes: int
    url: str | None = None


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for document storage backends."""

    async def save(self, key: str, data: bytes) -> StoredFile:
        """Store bytes under ``key`` and return metadata."""

    async def get(self, key: str) -> bytes:
        """Retrieve stored bytes for ``key``."""

    def stream(self, key: str) -> AsyncIterator[bytes]:
        """Read an object in bounded chunks."""

    async def delete(self, key: str) -> None:
        """Remove the object stored at ``key``."""

    async def exists(self, key: str) -> bool:
        """Return True if ``key`` exists."""

    def url(self, key: str, expires_in: int = 3600) -> str | None:
        """Return a (possibly presigned) URL for ``key``, or None."""


def _shard_key(sha256: str, filename: str) -> str:
    """Shard storage path by SHA-256 prefix to avoid flat-directory bloat."""
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}/{filename}"


class LocalFileStorage(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.STORAGE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, key: str) -> Path:
        return self.root / key

    async def save(self, key: str, data: bytes) -> StoredFile:
        full = self._full_path(key)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return StoredFile(path=key, size_bytes=len(data), url=str(full))

    async def get(self, key: str) -> bytes:
        return self._full_path(key).read_bytes()

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        with self._full_path(key).open("rb") as stored:
            while chunk := stored.read(64 * 1024):
                yield chunk

    async def delete(self, key: str) -> None:
        full = self._full_path(key)
        if full.exists():
            full.unlink()

    async def exists(self, key: str) -> bool:
        return self._full_path(key).exists()

    def url(self, key: str, expires_in: int = 3600) -> str | None:
        return str(self._full_path(key))


class S3Storage(StorageBackend):
    """S3 / MinIO compatible storage backend."""

    def __init__(
        self,
        bucket: str | None = None,
        client: BaseClient | None = None,
    ) -> None:
        self.bucket = bucket or settings.STORAGE_BUCKET or "documents"
        self._client = client or boto3.client("s3")

    async def save(self, key: str, data: bytes) -> StoredFile:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return StoredFile(
            path=key,
            size_bytes=len(data),
            url=self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=3600,
            ),
        )

    async def get(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()  # type: ignore[no-any-return]

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        body = self._client.get_object(Bucket=self.bucket, Key=key)["Body"]
        try:
            for chunk in body.iter_chunks(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self._client.exceptions.NoSuchKey:
            return False

    def url(self, key: str, expires_in: int = 3600) -> str | None:
        return self._client.generate_presigned_url(  # type: ignore[no-any-return]
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def get_storage() -> StorageBackend:
    """Factory returning the configured storage backend."""
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "s3":
        return S3Storage()
    return LocalFileStorage()
