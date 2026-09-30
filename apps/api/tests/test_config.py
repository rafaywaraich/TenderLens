from app.config import Settings


def test_normalizes_supabase_postgres_url_for_async_sqlalchemy() -> None:
    settings = Settings(database_url="postgresql://user:password@example.test/postgres")

    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_parses_multiple_cors_origins() -> None:
    settings = Settings(allowed_origins="https://one.test, https://two.test/")

    assert settings.cors_origins == ["https://one.test", "https://two.test"]


def test_cloud_storage_requires_server_credentials() -> None:
    settings = Settings(storage_provider="supabase")

    try:
        settings.validate_cloud_configuration()
    except ValueError as error:
        assert "SUPABASE_URL" in str(error)
    else:
        raise AssertionError("Expected missing cloud storage credentials to fail validation")


def test_prepared_statements_remain_enabled_for_session_pooler_by_default() -> None:
    settings = Settings(environment="production")

    assert settings.db_disable_prepared_statements is False
