from pathlib import Path

import pymupdf as fitz

from app.services import pdf as pdf_service


def test_extract_pages_uses_ocr_for_image_only_page(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "sample.pdf"
    pdf = fitz.open()
    text_page = pdf.new_page()
    text_page.insert_text((72, 72), "Mandatory insurance requirement " * 4)
    pdf.new_page()
    pdf.save(path)
    pdf.close()

    monkeypatch.setattr(pdf_service, "_ocr_page", lambda _: ("Scanned mandatory requirement text", 91.5))
    pages = pdf_service._extract_pages(path)

    assert len(pages) == 2
    assert pages[0]["ocr_required"] is False
    assert pages[0]["extraction_method"] == "embedded"
    assert pages[1]["extraction_method"] == "ocr"
    assert pages[1]["ocr_confidence"] == 91.5


def test_extract_pages_flags_failed_ocr_for_review(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "blank.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(path)
    pdf.close()

    monkeypatch.setattr(pdf_service, "_ocr_page", lambda _: ("", None))
    pages = pdf_service._extract_pages(path)

    assert pages[0]["ocr_required"] is True
    assert pages[0]["extraction_method"] == "embedded"


def test_extract_pages_rejects_pdf_over_demo_page_limit(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "large.pdf"
    pdf = fitz.open()
    for _ in range(3):
        pdf.new_page()
    pdf.save(path)
    pdf.close()

    monkeypatch.setattr(pdf_service.settings, "max_pdf_pages", 2)

    try:
        pdf_service._extract_pages(path)
    except ValueError as error:
        assert "2-page demo limit" in str(error)
    else:
        raise AssertionError("Expected the page limit to reject this PDF")

