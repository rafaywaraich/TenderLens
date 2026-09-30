from pathlib import Path
from urllib.parse import quote

import aiofiles
import httpx

from app.config import get_settings


settings = get_settings()


class StorageConfigurationError(RuntimeError):
    pass


def _supabase_headers() -> dict[str, str]:
    if not settings.supabase_service_role_key:
        raise StorageConfigurationError("Supabase service role key is not configured")
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }


def _local_path(key: str) -> Path:
    safe_parts = [part for part in Path(key).parts if part not in {"..", "."}]
    return settings.upload_dir.joinpath(*safe_parts)


async def store_pdf(source: Path, key: str) -> None:
    if settings.storage_provider == "local":
        destination = _local_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        return

    if settings.storage_provider != "supabase" or not settings.supabase_url:
        raise StorageConfigurationError(f"Unsupported storage provider: {settings.storage_provider}")

    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{quote(settings.supabase_storage_bucket, safe='')}/{quote(key, safe='/')}"
    )
    async with aiofiles.open(source, "rb") as pdf:
        content = await pdf.read()
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            headers={**_supabase_headers(), "Content-Type": "application/pdf", "x-upsert": "false"},
            content=content,
        )
        response.raise_for_status()


async def materialize_pdf(key: str, destination: Path) -> tuple[Path, bool]:
    if settings.storage_provider == "local":
        path = _local_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Stored PDF is missing: {key}")
        return path, False

    if settings.storage_provider != "supabase" or not settings.supabase_url:
        raise StorageConfigurationError(f"Unsupported storage provider: {settings.storage_provider}")

    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/authenticated/"
        f"{quote(settings.supabase_storage_bucket, safe='')}/{quote(key, safe='/')}"
    )
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(url, headers=_supabase_headers())
        response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(destination, "wb") as pdf:
        await pdf.write(response.content)
    return destination, True


async def delete_pdf(key: str) -> None:
    if settings.storage_provider == "local":
        path = _local_path(key)
        path.unlink(missing_ok=True)
        for parent in (path.parent, path.parent.parent):
            if parent != settings.upload_dir and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
        return

    if settings.storage_provider != "supabase" or not settings.supabase_url:
        raise StorageConfigurationError(f"Unsupported storage provider: {settings.storage_provider}")

    url = (
        f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
        f"{quote(settings.supabase_storage_bucket, safe='')}/{quote(key, safe='/')}"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.delete(url, headers=_supabase_headers())
        if response.status_code != 404:
            response.raise_for_status()
