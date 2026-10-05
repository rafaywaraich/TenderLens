import asyncio
import hashlib
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import engine, get_session, init_db
from app.models import Document, DocumentAnalysis, DocumentPage
from app.schemas import (
    DocumentAnalysisRead,
    DocumentRead,
    EmbeddingHealthRead,
    HealthRead,
    PageRead,
    ReadinessRead,
    SearchResultRead,
)
from app.services.analysis import analyze_document
from app.services.embeddings import EmbeddingUnavailableError, embed_query, embedding_health
from app.services.pdf import process_document, validate_pdf
from app.services.search import fuse_ranked_results, keyword_search, semantic_search
from app.services.storage import delete_pdf, store_pdf


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_cloud_configuration()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="TenderLens API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    return HealthRead(status="ok")


@app.get("/ready", response_model=ReadinessRead)
async def ready() -> ReadinessRead:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return ReadinessRead(
        status="ready",
        database="connected",
        storage=settings.storage_provider,
        embedding_provider=settings.embedding_provider,
    )


def require_demo_access(
    x_demo_access_code: str | None = Header(default=None),
) -> None:
    expected = settings.demo_access_code
    if expected and (not x_demo_access_code or not secrets.compare_digest(x_demo_access_code, expected)):
        raise HTTPException(status_code=401, detail="A valid demo access code is required")


@app.post("/documents", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: None = Depends(require_demo_access),
    session: AsyncSession = Depends(get_session),
) -> Document:
    filename = Path(file.filename or "document.pdf").name
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are supported")

    temporary_path = settings.upload_dir / f".{uuid4()}.upload"
    digest = hashlib.sha256()
    size = 0

    try:
        async with aiofiles.open(temporary_path, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    limit_mb = settings.max_upload_bytes // (1024 * 1024)
                    raise HTTPException(status_code=413, detail=f"PDF exceeds the {limit_mb} MB demo limit")
                digest.update(chunk)
                await target.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")

        try:
            await asyncio.to_thread(validate_pdf, temporary_path)
        except ValueError as exc:
            response_status = 413 if "page demo limit" in str(exc) else 400
            raise HTTPException(status_code=response_status, detail=str(exc)) from exc

        checksum = digest.hexdigest()
        existing = await session.scalar(select(Document).where(Document.sha256 == checksum))
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={"message": "This PDF has already been uploaded", "document_id": existing.id},
            )

        document_id = str(uuid4())
        storage_key = f"documents/{document_id}/original.pdf"
        await store_pdf(temporary_path, storage_key)

        document = Document(
            id=document_id,
            filename=filename,
            sha256=checksum,
            size_bytes=size,
            status="queued",
            storage_key=storage_key,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        background_tasks.add_task(process_document, document_id, storage_key)
        return document
    finally:
        await file.close()
        temporary_path.unlink(missing_ok=True)


@app.get("/documents", response_model=list[DocumentRead])
async def list_documents(session: AsyncSession = Depends(get_session)) -> list[Document]:
    result = await session.scalars(select(Document).order_by(Document.created_at.desc()))
    return list(result)


@app.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: str, session: AsyncSession = Depends(get_session)) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    _: None = Depends(require_demo_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait for processing to finish before deleting")

    storage_key = document.storage_key or f"{document_id}/original.pdf"
    await delete_pdf(storage_key)
    await session.delete(document)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/documents/{document_id}/reprocess", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_demo_access),
    session: AsyncSession = Depends(get_session),
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Document is already being processed")

    storage_key = document.storage_key or f"{document_id}/original.pdf"

    existing_analysis = await session.get(DocumentAnalysis, document_id)
    if existing_analysis is not None:
        await session.delete(existing_analysis)
    document.status = "queued"
    document.error_message = None
    await session.commit()
    await session.refresh(document)
    background_tasks.add_task(process_document, document_id, storage_key)
    return document


@app.get("/documents/{document_id}/pages", response_model=list[PageRead])
async def list_document_pages(
    document_id: str, session: AsyncSession = Depends(get_session)
) -> list[DocumentPage]:
    if await session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await session.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    )
    return list(result)


@app.get("/documents/{document_id}/analysis", response_model=DocumentAnalysisRead)
async def get_document_analysis(
    document_id: str, session: AsyncSession = Depends(get_session)
) -> DocumentAnalysis | DocumentAnalysisRead:
    if await session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    analysis = await session.get(DocumentAnalysis, document_id)
    if analysis is None:
        return DocumentAnalysisRead(document_id=document_id, status="not_started")
    return analysis


@app.post(
    "/documents/{document_id}/analysis",
    response_model=DocumentAnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_document_analysis(
    document_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_demo_access),
    session: AsyncSession = Depends(get_session),
) -> DocumentAnalysis:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status != "ready":
        raise HTTPException(status_code=409, detail="Wait for document processing to finish")

    analysis = await session.get(DocumentAnalysis, document_id)
    if analysis is not None and analysis.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Tender analysis is already running")
    if analysis is None:
        analysis = DocumentAnalysis(document_id=document_id)
        session.add(analysis)
    analysis.status = "queued"
    analysis.error_message = None
    analysis.content = None
    analysis.model = settings.analysis_model
    await session.commit()
    await session.refresh(analysis)
    background_tasks.add_task(analyze_document, document_id)
    return analysis


@app.get("/search", response_model=list[SearchResultRead])
async def search_pages(
    q: str = Query(min_length=2, max_length=200),
    document_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[SearchResultRead]:
    keyword_rows = await keyword_search(session, q, document_id)
    semantic_rows = []
    try:
        semantic_rows = await semantic_search(session, await embed_query(q), document_id)
    except EmbeddingUnavailableError:
        pass

    fused = fuse_ranked_results(keyword_rows, semantic_rows, limit)
    return [
        SearchResultRead(
            document_id=item["document_id"],
            filename=item["filename"],
            page_number=item["page_number"],
            snippet=item["snippet"],
            rank=item["hybrid_score"],
            extraction_method=item["extraction_method"],
            ocr_confidence=item["ocr_confidence"],
            retrieval_method=item["retrieval_method"],
            semantic_similarity=item.get("semantic_similarity"),
        )
        for item in fused
    ]


@app.get("/embeddings/health", response_model=EmbeddingHealthRead)
async def get_embedding_health() -> EmbeddingHealthRead:
    dimensions, error = await embedding_health()
    return EmbeddingHealthRead(
        status="ok" if error is None else "unavailable",
        model=settings.embedding_model,
        dimensions=dimensions or None,
        detail=error,
    )

