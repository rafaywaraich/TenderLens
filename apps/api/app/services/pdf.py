import asyncio
from pathlib import Path

import pymupdf as fitz
import pytesseract
from PIL import Image
from pytesseract import Output
from sqlalchemy import delete, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Document, DocumentPage
from app.services.embeddings import embed_document_pages
from app.services.storage import materialize_pdf


settings = get_settings()


def validate_pdf(path: Path) -> int:
    try:
        with fitz.open(path) as pdf:
            if pdf.needs_pass:
                raise ValueError("Password-protected PDFs are not supported yet")
            if pdf.page_count > settings.max_pdf_pages:
                raise ValueError(f"PDF exceeds the {settings.max_pdf_pages}-page demo limit")
            return pdf.page_count
    except fitz.FileDataError as exc:
        raise ValueError("The uploaded file is not a valid PDF") from exc


def _ocr_page(page: fitz.Page) -> tuple[str, float | None]:
    pixmap = page.get_pixmap(dpi=settings.ocr_dpi, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    data = pytesseract.image_to_data(image, lang=settings.ocr_language, output_type=Output.DICT)

    words: list[str] = []
    confidences: list[float] = []
    for word, confidence in zip(data["text"], data["conf"]):
        cleaned = word.strip()
        try:
            numeric_confidence = float(confidence)
        except (TypeError, ValueError):
            numeric_confidence = -1
        if cleaned:
            words.append(cleaned)
        if cleaned and numeric_confidence >= 0:
            confidences.append(numeric_confidence)

    text = " ".join(words)
    mean_confidence = sum(confidences) / len(confidences) if confidences else None
    return text, mean_confidence


def _extract_pages(path: Path) -> list[dict[str, object]]:
    validate_pdf(path)
    extracted: list[dict[str, object]] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf):
            text = page.get_text("text").strip()
            extraction_method = "embedded"
            ocr_confidence = None

            if settings.ocr_enabled and len(text) < settings.minimum_embedded_text_chars:
                ocr_text, ocr_confidence = _ocr_page(page)
                if len(ocr_text) > len(text):
                    text = ocr_text
                    extraction_method = "ocr"

            extracted.append(
                {
                    "page_number": index + 1,
                    "text": text,
                    "char_count": len(text),
                    "ocr_required": len(text) < settings.minimum_embedded_text_chars,
                    "extraction_method": extraction_method,
                    "ocr_confidence": ocr_confidence if extraction_method == "ocr" else None,
                }
            )
    return extracted


async def process_document(document_id: str, storage_key: str) -> None:
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = "processing"
        document.error_message = None
        await session.commit()

    temporary_path = settings.upload_dir / ".processing" / f"{document_id}.pdf"
    remove_when_done = False
    try:
        path, remove_when_done = await materialize_pdf(storage_key, temporary_path)
        pages = await asyncio.to_thread(_extract_pages, path)
        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            if document is None:
                return

            await session.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
            session.add_all(DocumentPage(document_id=document_id, **page) for page in pages)
            document.page_count = len(pages)
            document.status = "ready"
            document.embedding_status = "pending"
            document.embedding_error = None
            await session.commit()
        await embed_document_pages(document_id, pages)
    except Exception as exc:
        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            if document is not None:
                document.status = "failed"
                document.error_message = str(exc)[:2000]
                await session.commit()
    finally:
        if remove_when_done:
            temporary_path.unlink(missing_ok=True)

