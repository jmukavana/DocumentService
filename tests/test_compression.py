"""Tests for compression service."""

import asyncio
import gzip

from app.services.compression import CompressionAlgo, compress, decompress, decompress_chunks


def test_compress_text_gzip():
    """Compressible text uses gzip and shrinks."""
    data = b"hello world " * 100
    result = compress(data, "text/plain", level=6)
    assert result.algorithm == CompressionAlgo.gzip
    assert result.compressed_size < result.original_size
    assert result.compression_ratio < 1.0


def test_compress_small_returns_none():
    """Tiny data that doesn't benefit from compression returns algo=none."""
    data = b"hi"
    result = compress(data, "text/plain", level=6)
    assert result.algorithm == CompressionAlgo.none
    assert result.compression_ratio == 1.0


def test_compress_decompress_roundtrip():
    """Decompress restores original bytes."""
    original = b"The quick brown fox jumps over the lazy dog." * 50
    result = compress(original, "text/plain", level=9)
    restored = decompress(result.data, result.algorithm)
    assert restored == original


def test_compress_none_for_incompressible_mime():
    """Non-compressible MIME (e.g. image) returns algo=none unchanged."""
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000
    result = compress(data, "image/png", level=6)
    assert result.algorithm == CompressionAlgo.none
    assert result.data == data


def test_decompress_none_returns_as_is():
    """Decompress with algo=none returns input unchanged."""
    data = b"raw bytes"
    assert decompress(data, CompressionAlgo.none) == data


def test_compression_level_range():
    """Level clamped to 0-9."""
    data = b"compressible content " * 200
    r0 = compress(data, "text/plain", level=0)
    r9 = compress(data, "text/plain", level=9)
    # Higher level should be <= lower level size
    assert r9.compressed_size <= r0.compressed_size


def test_compress_empty_bytes():
    """Empty input handled gracefully."""
    result = compress(b"", "text/plain", level=6)
    assert result.original_size == 0
    assert result.compressed_size == 0


def test_pdf_compression_round_trip():
    original = b"%PDF-1.4\n" + b"repeated PDF data " * 200
    result = compress(original, "application/pdf", level=6)
    assert result.algorithm == CompressionAlgo.gzip
    assert decompress(result.data, result.algorithm) == original


def test_legacy_pdf_compression_round_trip():
    original = b"%PDF-1.4\nlegacy payload"
    assert decompress(gzip.compress(original), CompressionAlgo.pdf) == original


def test_chunked_pdf_decompression():
    original = b"%PDF-1.4\n" + b"many pages " * 1000
    compressed = gzip.compress(original)

    async def chunks():
        for offset in range(len(compressed)):
            yield compressed[offset:offset + 1]

    async def restore():
        return b"".join([chunk async for chunk in decompress_chunks(
            chunks(), CompressionAlgo.pdf
        )])

    assert asyncio.run(restore()) == original
