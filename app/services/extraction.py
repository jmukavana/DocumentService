"""Content extraction for OCR images and documents with embedded text."""

from __future__ import annotations

import email.policy
import io
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import PurePath
from xml.etree import ElementTree

from app.core.config import settings
from app.worker.tasks import extract_ocr

TEXT_EXTENSIONS = {
    ".txt", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".md", ".yaml",
    ".yml", ".log", ".sql", ".py", ".js", ".ts", ".css", ".sh", ".ini",
    ".cfg", ".toml", ".svg",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub"}


def _office_suffix(data: bytes, suffix: str) -> str:
    if suffix in OFFICE_EXTENSIONS:
        return suffix
    if not data.startswith(b"PK\x03\x04"):
        return suffix
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" in names:
                return ".docx"
            if "xl/workbook.xml" in names:
                return ".xlsx"
            if "ppt/presentation.xml" in names:
                return ".pptx"
            if "META-INF/container.xml" in names:
                return ".epub"
            if "mimetype" in names:
                marker = archive.read("mimetype")[:150]
                for ending, extension in ((b"text", ".odt"), (b"spreadsheet", ".ods"),
                                          (b"presentation", ".odp")):
                    if marker.endswith(ending):
                        return extension
    except zipfile.BadZipFile:
        pass
    return suffix


def detect_mime_type(data: bytes, filename: str, reported: str | None) -> str:
    """Prefer recognizable file signatures to a client's Content-Type header."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        office = _office_suffix(data, PurePath(filename.lower()).suffix)
        if office in OFFICE_EXTENSIONS:
            return mimetypes.guess_type(f"file{office}")[0] or "application/zip"
    signatures = (
        (b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF8", "image/gif"), (b"BM", "image/bmp"),
        (b"II*\x00", "image/tiff"), (b"MM\x00*", "image/tiff"),
    )
    for signature, mime in signatures:
        if data.startswith(signature):
            return mime
    guessed, _ = mimetypes.guess_type(filename)
    if reported and reported != "application/octet-stream":
        return reported
    return guessed or reported or "application/octet-stream"


class UnsupportedExtractionFormat(ValueError):
    """The file can be stored, but no extractor can read its content."""


@dataclass(frozen=True)
class ContentExtraction:
    text: str
    page_count: int
    confidence: float
    method: str


def _xml_text(data: bytes, text_tags: set[str], break_tags: set[str]) -> str:
    root = ElementTree.fromstring(data)
    chunks: list[str] = []
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in text_tags and element.text:
            chunks.append(element.text)
        elif name in break_tags:
            chunks.append("\n")
    return re.sub(r"\n[ \t]*\n+", "\n", "".join(chunks)).strip()


def _office_text(data: bytes, suffix: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(item.file_size for item in archive.infolist()) > settings.MAX_FILE_SIZE_BYTES:
            raise ValueError("Document expands beyond the configured size limit")
        names = archive.namelist()
        if suffix == ".docx":
            parts = [name for name in names if name == "word/document.xml"]
            parts += [name for name in names if name.startswith("word/header") or name.startswith("word/footer")]
            return "\n".join(_xml_text(archive.read(name), {"t"}, {"p", "tr"}) for name in parts)
        if suffix == ".pptx":
            parts = sorted(name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
            return "\n\n".join(_xml_text(archive.read(name), {"t"}, {"p"}) for name in parts)
        if suffix == ".xlsx":
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(n.text or "" for n in item.iter() if n.tag.endswith("}t"))
                          for item in root if item.tag.endswith("}si")]
            sheets: list[str] = []
            for name in sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)):
                root = ElementTree.fromstring(archive.read(name))
                rows: list[str] = []
                for row in root.iter():
                    if not row.tag.endswith("}row"):
                        continue
                    values: list[str] = []
                    for cell in row:
                        if not cell.tag.endswith("}c"):
                            continue
                        value = next((n.text for n in cell.iter() if n.tag.endswith("}v") or
                                      n.tag.endswith("}t")), None)
                        if value is not None:
                            if cell.get("t") == "s":
                                value = shared[int(value)]
                            values.append(value)
                    if values:
                        rows.append("\t".join(values))
                sheets.append("\n".join(rows))
            return "\n\n".join(sheets)
        if suffix in {".odt", ".ods", ".odp"}:
            return _xml_text(archive.read("content.xml"), {"p", "span", "h"}, {"table-row"})
        if suffix == ".epub":
            parts = sorted(name for name in names if name.lower().endswith((".xhtml", ".html", ".htm")))
            return "\n\n".join(_xml_text(archive.read(name), {"p", "h1", "h2", "h3", "li"},
                                           {"br"}) for name in parts)
    raise UnsupportedExtractionFormat("Unsupported Office format")


def extract_content(data: bytes, filename: str, mime_type: str, language: str) -> ContentExtraction:
    """Choose a parser by file signature and name, keeping OCR for raster content."""
    suffix = _office_suffix(data, PurePath(filename.lower()).suffix)
    mime_type = detect_mime_type(data, filename, mime_type)
    if data.startswith(b"%PDF-") or mime_type == "application/pdf" or suffix == ".pdf":
        result = extract_ocr(data, "application/pdf", language)
        return ContentExtraction(result.text, result.page_count, result.confidence, "ocr")
    if data.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*")) or (
        mime_type.startswith("image/") and suffix != ".svg"
    ) or suffix in IMAGE_EXTENSIONS:
        result = extract_ocr(data, "image/auto", language)
        return ContentExtraction(result.text, result.page_count, result.confidence, "ocr")
    if suffix in OFFICE_EXTENSIONS or data.startswith(b"PK\x03\x04"):
        if suffix not in OFFICE_EXTENSIONS:
            raise UnsupportedExtractionFormat("Unknown ZIP document format")
        return ContentExtraction(_office_text(data, suffix), 1, 1.0, "embedded_text")
    if suffix == ".eml" or mime_type == "message/rfc822":
        message = BytesParser(policy=email.policy.default).parsebytes(data)
        bodies = [part.get_content() for part in message.walk()
                  if part.get_content_type() == "text/plain" and not part.get_filename()]
        return ContentExtraction("\n".join(str(body) for body in bodies), 1, 1.0,
                                 "embedded_text")
    if mime_type.startswith("text/") or suffix in TEXT_EXTENSIONS or mime_type in {
        "application/json", "application/xml", "application/javascript",
    } or (not suffix and mime_type == "application/octet-stream"):
        if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise UnsupportedExtractionFormat("Binary data cannot be decoded as text")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = data.decode("utf-16")
            except UnicodeError as exc:
                raise UnsupportedExtractionFormat("Text encoding is unsupported") from exc
        return ContentExtraction(content, 1, 1.0, "embedded_text")
    if b"\x00" not in data[:4096]:
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
        else:
            if content and sum(ch.isprintable() or ch in "\r\n\t" for ch in content) / len(content) > 0.95:
                return ContentExtraction(content, 1, 1.0, "embedded_text")
    raise UnsupportedExtractionFormat("No extractor is available for this file format")
