"""Pure service behavior that needs no database."""

from app.services.document import searchable_text, supports_ocr


def test_text_upload_is_searchable_without_ocr():
    assert not supports_ocr("text/plain")
    assert "quarterly report" in searchable_text("report.txt", "text/plain",
                                                  b"quarterly report")


def test_images_and_pdfs_use_ocr():
    assert supports_ocr("application/pdf")
    assert supports_ocr("image/png")
