"""Compression service.

- gzip / zlib for general files
- pikepdf (qpdf) structural optimization for PDFs when ENABLE_PDF_OPTIMIZE is on
"""

from __future__ import annotations

import gzip
import io
import zlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pikepdf

from app.core.config import settings
from app.models.document import CompressionAlgo

# MIME types that benefit from text/binary stream compression.
_COMPRESSIBLE_MIMES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/json",
    "application/json",
    "text/xml",
    "application/xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True)
class CompressedResult:
    data: bytes
    algorithm: CompressionAlgo
    original_size: int
    compressed_size: int

    @property
    def compression_ratio(self) -> float:
        if self.original_size == 0:
            return 0.0
        return self.compressed_size / self.original_size


def _is_pdf(mime_type: str) -> bool:
    return mime_type == "application/pdf"


def _optimize_pdf(data: bytes, level: int) -> bytes:
    """Structural PDF optimization via pikepdf/qpdf.

    Downsample images, recompress Flat streams, remove duplicate objects,
    and linearize for fast web view. Falls back to input on any error.
    """
    if not settings.ENABLE_PDF_OPTIMIZE:
        return data
    try:
        input_pdf = pikepdf.open(io.BytesIO(data))
        output = io.BytesIO()
        pikepdf.settings.set_flate_compression_level(level)  # type: ignore[arg-type]
        input_pdf.save(output, linearize=True, object_stream_mode="generate")  # type: ignore[arg-type]
        input_pdf.close()
        optimized = output.getvalue()
        # Only use optimized result if it is actually smaller.
        if len(optimized) < len(data):
            return optimized
    except Exception:  # noqa: BLE001 - structural PDF repair is best-effort
        pass
    return data


def compress(
    data: bytes,
    mime_type: str,
    level: int | None = None,
) -> CompressedResult:
    """Compress ``data`` according to its MIME type.

    PDFs: optional pikepdf structural optimization, then gzip.
    Other compressible MIMEs: gzip (or zlib when level >= 9).
    Everything else: stored uncompressed (algo=none).
    """
    level = level if level is not None else settings.DEFAULT_COMPRESSION_LEVEL
    level = max(0, min(9, level))
    original_size = len(data)

    if not _compressible(mime_type):
        return CompressedResult(
            data=data,
            algorithm=CompressionAlgo.none,
            original_size=original_size,
            compressed_size=original_size,
        )

    # PDF-specific structural optimization first.
    payload = data
    if _is_pdf(mime_type):
        payload = _optimize_pdf(data, level)

    if level >= 9:
        compressed = zlib.compress(payload, level=level)
        algo = CompressionAlgo.zlib
    else:
        compressed = gzip.compress(payload, compresslevel=level)
        algo = CompressionAlgo.gzip

    # Only keep compression if it shrinks the payload.
    if len(compressed) < len(payload):
        return CompressedResult(
            data=compressed,
            algorithm=algo,
            original_size=original_size,
            compressed_size=len(compressed),
        )

    return CompressedResult(
        data=payload,
        algorithm=CompressionAlgo.none,
        original_size=original_size,
        compressed_size=len(payload),
    )


def decompress(data: bytes, algorithm: CompressionAlgo) -> bytes:
    """Reverse :func:`compress`."""
    if algorithm == CompressionAlgo.gzip:
        return gzip.decompress(data)
    if algorithm == CompressionAlgo.zlib:
        return zlib.decompress(data)
    if algorithm == CompressionAlgo.pdf:
        # Older uploads marked gzipped PDFs as "pdf"; support both forms.
        return gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data
    return data


async def decompress_chunks(
    chunks: AsyncIterator[bytes], algorithm: CompressionAlgo
) -> AsyncIterator[bytes]:
    """Decompress stored chunks without loading the whole document."""
    if algorithm == CompressionAlgo.pdf:
        first = b""
        while len(first) < 2:
            chunk = await anext(chunks, b"")
            if not chunk:
                break
            first += chunk
        if not first.startswith(b"\x1f\x8b"):
            if first:
                yield first
            async for chunk in chunks:
                yield chunk
            return
        algorithm = CompressionAlgo.gzip
        chunks = _prepend_chunk(first, chunks)

    if algorithm == CompressionAlgo.none:
        async for chunk in chunks:
            yield chunk
        return

    decoder = zlib.decompressobj(
        16 + zlib.MAX_WBITS if algorithm == CompressionAlgo.gzip else zlib.MAX_WBITS
    )
    async for chunk in chunks:
        if output := decoder.decompress(chunk):
            yield output
    if output := decoder.flush():
        yield output
    if not decoder.eof:
        raise ValueError("Truncated compressed document")


async def _prepend_chunk(first: bytes, chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    yield first
    async for chunk in chunks:
        yield chunk


def _compressible(mime_type: str) -> bool:
    base = mime_type.split(";")[0].strip().lower()
    if base in _COMPRESSIBLE_MIMES:
        return True
    return base.startswith("text/")
