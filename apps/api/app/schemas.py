from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    id: str
    filename: str
    sha256: str
    size_bytes: int
    page_count: int | None
    status: str
    error_message: str | None
    embedding_status: str
    embedding_error: str | None
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimensions: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PageRead(BaseModel):
    page_number: int
    text: str
    char_count: int
    ocr_required: bool
    extraction_method: str
    ocr_confidence: float | None

    model_config = ConfigDict(from_attributes=True)


class HealthRead(BaseModel):
    status: str


class ReadinessRead(BaseModel):
    status: str
    database: str
    storage: str
    embedding_provider: str


class SearchResultRead(BaseModel):
    document_id: str
    filename: str
    page_number: int
    snippet: str
    rank: float
    extraction_method: str
    ocr_confidence: float | None
    retrieval_method: str
    semantic_similarity: float | None = None


class EmbeddingHealthRead(BaseModel):
    status: str
    model: str
    dimensions: int | None = None
    detail: str | None = None

