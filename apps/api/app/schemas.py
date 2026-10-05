from datetime import datetime
from typing import Literal

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


class CompanyProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    capabilities: str = Field(min_length=1, max_length=6000)
    registrations: str = Field(default="", max_length=4000)
    experience: str = Field(default="", max_length=4000)
    financial_capacity: str = Field(default="", max_length=4000)
    available_documents: str = Field(default="", max_length=4000)
    constraints: str = Field(default="", max_length=4000)


class RequirementComparison(BaseModel):
    requirement_id: str
    status: Literal["met", "unmet", "unknown"]
    reason: str = Field(min_length=1, max_length=3000)
    profile_evidence: str = Field(max_length=3000)
    profile_fields: list[Literal[
        "capabilities", "registrations", "experience", "financial_capacity",
        "available_documents", "constraints",
    ]] = Field(default_factory=list)
    missing_information: str = Field(default="", max_length=3000)
    suggested_input: str = Field(default="", max_length=3000)


class EnteredProfileInfo(BaseModel):
    field: str
    value: str


class AssessmentComparison(RequirementComparison):
    category: str
    label: str
    requirement: str
    page_numbers: list[int]
    mandatory: bool
    entered_information: list[EnteredProfileInfo] = Field(default_factory=list)


class AssessmentContent(BaseModel):
    company_name: str
    recommendation: Literal["bid", "no_bid", "review_required"]
    score: int
    coverage: int
    summary: str
    comparisons: list[AssessmentComparison]
    evaluated_on: str


class AssessmentRead(BaseModel):
    document_id: str
    status: str
    error_message: str | None = None
    model: str | None = None
    profile: CompanyProfile | None = None
    content: AssessmentContent | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

