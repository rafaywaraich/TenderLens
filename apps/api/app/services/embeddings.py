from collections.abc import Sequence

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal
from app.models import Document


settings = get_settings()


class EmbeddingUnavailableError(RuntimeError):
    pass


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def _validate_embeddings(embeddings: object, expected_count: int) -> list[list[float]]:
    if not isinstance(embeddings, list) or len(embeddings) != expected_count:
        raise EmbeddingUnavailableError("Embedding provider returned an invalid response")
    vectors = [item for item in embeddings if isinstance(item, list)]
    if len(vectors) != expected_count or any(
        len(vector) != settings.embedding_dimensions for vector in vectors
    ):
        received = len(vectors[0]) if vectors else 0
        raise EmbeddingUnavailableError(
            f"Expected {settings.embedding_dimensions} dimensions, received {received}"
        )
    return vectors


async def _embed_ollama(inputs: list[str]) -> list[list[float]]:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/embed",
                json={"model": settings.embedding_model, "input": inputs},
            )
            response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        raise EmbeddingUnavailableError(f"Ollama embedding service unavailable: {exc}") from exc
    return _validate_embeddings(response.json().get("embeddings"), len(inputs))


async def _embed_gemini(inputs: list[str]) -> list[list[float]]:
    if not settings.gemini_api_key:
        raise EmbeddingUnavailableError("GEMINI_API_KEY is not configured")
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.embedding_model}:embedContent"
    )
    vectors: list[list[float]] = []
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            for value in inputs:
                response = await client.post(
                    endpoint,
                    headers={"x-goog-api-key": settings.gemini_api_key},
                    json={
                        "content": {"parts": [{"text": value}]},
                        "output_dimensionality": settings.embedding_dimensions,
                    },
                )
                response.raise_for_status()
                vectors.append(response.json().get("embedding", {}).get("values"))
    except (httpx.HTTPError, OSError, AttributeError) as exc:
        raise EmbeddingUnavailableError(f"Gemini embedding service unavailable: {exc}") from exc
    return _validate_embeddings(vectors, len(inputs))


async def _embed(inputs: list[str]) -> list[list[float]]:
    if settings.embedding_provider == "ollama":
        return await _embed_ollama(inputs)
    if settings.embedding_provider == "gemini":
        return await _embed_gemini(inputs)
    raise EmbeddingUnavailableError(f"Unsupported embedding provider: {settings.embedding_provider}")


def _query_input(query: str) -> str:
    content = query[: settings.embedding_max_chars]
    if settings.embedding_provider == "gemini" and settings.embedding_model == "gemini-embedding-2":
        return f"task: search result | query: {content}"
    return f"search_query: {content}"


def _document_input(content: str) -> str:
    content = content[: settings.embedding_max_chars]
    if settings.embedding_provider == "gemini" and settings.embedding_model == "gemini-embedding-2":
        return f"title: none | text: {content}"
    return f"search_document: {content}"


async def embed_query(query: str) -> list[float]:
    return (await _embed([_query_input(query)]))[0]


async def embed_document_pages(document_id: str, pages: list[dict[str, object]]) -> None:
    candidates = [
        (int(page["page_number"]), str(page["text"]))
        for page in pages
        if len(str(page["text"]).strip()) >= 2
    ]
    async with SessionLocal() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.embedding_status = "processing"
        document.embedding_error = None
        await session.commit()

    try:
        for offset in range(0, len(candidates), settings.embedding_batch_size):
            batch = candidates[offset : offset + settings.embedding_batch_size]
            embeddings = await _embed([_document_input(content) for _, content in batch])
            async with SessionLocal() as session:
                for (page_number, _), embedding in zip(batch, embeddings):
                    await session.execute(
                        text(
                            f"UPDATE document_pages SET embedding = CAST(:embedding AS {settings.vector_sql_type}) "
                            "WHERE document_id = :document_id AND page_number = :page_number"
                        ),
                        {
                            "embedding": vector_literal(embedding),
                            "document_id": document_id,
                            "page_number": page_number,
                        },
                    )
                await session.commit()

        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            if document is not None:
                document.embedding_status = "ready"
                document.embedding_error = None
                document.embedding_provider = settings.embedding_provider
                document.embedding_model = settings.embedding_model
                document.embedding_dimensions = settings.embedding_dimensions
                await session.commit()
    except EmbeddingUnavailableError as exc:
        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            if document is not None:
                document.embedding_status = "unavailable"
                document.embedding_error = str(exc)[:2000]
                await session.commit()


async def embedding_health() -> tuple[int, str | None]:
    try:
        vector = await embed_query("TenderLens health check")
        return len(vector), None
    except EmbeddingUnavailableError as exc:
        return 0, str(exc)
