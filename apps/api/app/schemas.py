from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class AnalysisFinding(BaseModel):
    label: str = Field(description="Short heading for the evidence finding")
    detail: str = Field(description="Concise explanation grounded only in the tender text")
    page_numbers: list[int] = Field(description="One-based tender pages supporting the finding")


class AnalysisContent(BaseModel):
    overview: AnalysisFinding
    important_dates: list[AnalysisFinding]
    eligibility: list[AnalysisFinding]
    mandatory_requirements: list[AnalysisFinding]
    required_documents: list[AnalysisFinding]
    financial_conditions: list[AnalysisFinding]
    deliverables: list[AnalysisFinding]
    risks: list[AnalysisFinding]


class DocumentAnalysisRead(BaseModel):
    document_id: str
    status: str
    error_message: str | None = None
    model: str | None = None
    content: AnalysisContent | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

