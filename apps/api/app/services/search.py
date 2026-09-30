from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Document, DocumentPage
from app.services.embeddings import vector_literal


settings = get_settings()
RRF_K = 60


def fuse_ranked_results(
    keyword_rows: Sequence[dict[str, Any]], semantic_rows: Sequence[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    fused: dict[int, dict[str, Any]] = {}
    for position, row in enumerate(keyword_rows, start=1):
        item = dict(row)
        item["hybrid_score"] = 1.0 / (RRF_K + position)
        item["keyword_match"] = True
        item["semantic_match"] = False
        fused[int(item["page_id"])] = item

    for position, row in enumerate(semantic_rows, start=1):
        page_id = int(row["page_id"])
        if page_id in fused:
            fused[page_id]["hybrid_score"] += 1.0 / (RRF_K + position)
            fused[page_id]["semantic_match"] = True
            fused[page_id]["semantic_similarity"] = row.get("semantic_similarity")
        else:
            item = dict(row)
            item["hybrid_score"] = 1.0 / (RRF_K + position)
            item["keyword_match"] = False
            item["semantic_match"] = True
            fused[page_id] = item

    ranked = sorted(fused.values(), key=lambda item: item["hybrid_score"], reverse=True)[:limit]
    for item in ranked:
        if item["keyword_match"] and item["semantic_match"]:
            item["retrieval_method"] = "hybrid"
        elif item["semantic_match"]:
            item["retrieval_method"] = "semantic"
        else:
            item["retrieval_method"] = "keyword"
    return ranked


async def keyword_search(session: AsyncSession, query: str, document_id: str | None) -> list[dict[str, Any]]:
    configuration = literal_column("'english'")
    search_query = func.websearch_to_tsquery(configuration, query)
    document_vector = func.to_tsvector(configuration, DocumentPage.text)
    rank = func.ts_rank_cd(document_vector, search_query).label("keyword_score")
    snippet = func.ts_headline(
        configuration,
        DocumentPage.text,
        search_query,
        "StartSel=[[[, StopSel=]]], MaxFragments=2, FragmentDelimiter= … , MaxWords=35, MinWords=12",
    ).label("snippet")
    statement = (
        select(
            DocumentPage.id.label("page_id"),
            DocumentPage.document_id,
            Document.filename,
            DocumentPage.page_number,
            snippet,
            rank,
            DocumentPage.extraction_method,
            DocumentPage.ocr_confidence,
        )
        .join(Document, Document.id == DocumentPage.document_id)
        .where(document_vector.bool_op("@@")(search_query))
        .order_by(rank.desc(), DocumentPage.page_number)
        .limit(50)
    )
    if document_id is not None:
        statement = statement.where(DocumentPage.document_id == document_id)
    return [dict(row._mapping) for row in (await session.execute(statement)).all()]


async def semantic_search(
    session: AsyncSession, embedding: Sequence[float], document_id: str | None
) -> list[dict[str, Any]]:
    document_filter = "AND p.document_id = :document_id" if document_id is not None else ""
    statement = text(
        f"""
        SELECT p.id AS page_id, p.document_id, d.filename, p.page_number,
               LEFT(p.text, 420) AS snippet,
               1 - (p.embedding <=> CAST(:embedding AS {settings.vector_sql_type})) AS semantic_similarity,
               p.extraction_method, p.ocr_confidence
        FROM document_pages p
        JOIN documents d ON d.id = p.document_id
        WHERE p.embedding IS NOT NULL
          AND d.embedding_provider = :embedding_provider
          AND d.embedding_model = :embedding_model
          AND d.embedding_dimensions = :embedding_dimensions
          AND 1 - (p.embedding <=> CAST(:embedding AS {settings.vector_sql_type})) >= :minimum_similarity
          {document_filter}
        ORDER BY p.embedding <=> CAST(:embedding AS {settings.vector_sql_type})
        LIMIT 50
        """
    )
    parameters = {
        "embedding": vector_literal(embedding),
        "minimum_similarity": settings.semantic_min_similarity,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "document_id": document_id,
    }
    return [dict(row._mapping) for row in (await session.execute(statement, parameters)).all()]

