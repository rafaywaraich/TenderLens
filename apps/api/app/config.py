from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://tenderlens:tenderlens@localhost:5432/tenderlens"
    db_disable_prepared_statements: bool = False
    upload_dir: Path = Path("data/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 50
    storage_provider: str = "local"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "tender-pdfs"
    allowed_origins: str = "http://localhost:3000"
    demo_access_code: str | None = None
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_dpi: int = 250
    minimum_embedded_text_chars: int = 50
    ollama_base_url: str = "http://host.docker.internal:11434"
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    gemini_api_key: str | None = None
    analysis_model: str = "gemini-3.5-flash-lite"
    analysis_max_chars: int = 120000
    analysis_page_max_chars: int = 6000
    embedding_dimensions: int = 768
    pgvector_schema: str = "public"
    embedding_batch_size: int = 16
    embedding_max_chars: int = 7000
    semantic_min_similarity: float = 0.25

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.allowed_origins.split(",") if origin.strip()]

    @field_validator("pgvector_schema")
    @classmethod
    def validate_pgvector_schema(cls, value: str) -> str:
        if not value.replace("_", "").isalnum():
            raise ValueError("PGVECTOR_SCHEMA must be a simple PostgreSQL identifier")
        return value

    @property
    def vector_sql_type(self) -> str:
        return f"{self.pgvector_schema}.vector"

    def validate_cloud_configuration(self) -> None:
        if self.storage_provider == "supabase" and not (
            self.supabase_url and self.supabase_service_role_key
        ):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Supabase storage"
            )
        if self.embedding_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for Gemini embeddings")


@lru_cache
def get_settings() -> Settings:
    return Settings()

