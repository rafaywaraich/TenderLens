from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0} if settings.db_disable_prepared_statements else {},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.pgvector_schema}"))
        await connection.execute(
            text(f"CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA {settings.pgvector_schema}")
        )
        await connection.run_sync(Base.metadata.create_all)
        # Idempotent MVP migration for databases created before OCR support.
        await connection.execute(
            text(
                "ALTER TABLE document_pages "
                "ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(32) NOT NULL DEFAULT 'embedded'"
            )
        )
        await connection.execute(
            text("ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS ocr_confidence DOUBLE PRECISION")
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_pages_fts "
                "ON document_pages USING GIN (to_tsvector('english', text))"
            )
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_status VARCHAR(32) NOT NULL DEFAULT 'pending'")
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_error TEXT")
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_key VARCHAR(768)")
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(32)")
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(128)")
        )
        await connection.execute(
            text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER")
        )
        await connection.execute(
            text(
                "UPDATE documents SET embedding_provider = :provider, embedding_model = :model, "
                "embedding_dimensions = :dimensions WHERE embedding_status = 'ready' "
                "AND embedding_provider IS NULL"
            ),
            {
                "provider": settings.embedding_provider,
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
            },
        )
        await connection.execute(
            text(
                "ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS embedding "
                f"{settings.vector_sql_type}({settings.embedding_dimensions})"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_pages_embedding_hnsw "
                f"ON document_pages USING hnsw (embedding {settings.pgvector_schema}.vector_cosine_ops) "
                "WHERE embedding IS NOT NULL"
            )
        )
        await connection.execute(
            text(
                "UPDATE documents SET status = 'failed', "
                "error_message = 'Processing was interrupted; use Reprocess to retry' "
                "WHERE status IN ('queued', 'processing') "
                "AND updated_at < CURRENT_TIMESTAMP - INTERVAL '10 minutes'"
            )
        )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

