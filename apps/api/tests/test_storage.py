from pathlib import Path

from app.services import storage


async def test_local_storage_delete_removes_pdf_and_empty_directories(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(storage.settings, "storage_provider", "local")
    monkeypatch.setattr(storage.settings, "upload_dir", tmp_path)
    path = tmp_path / "documents" / "document-1" / "original.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"pdf")

    await storage.delete_pdf("documents/document-1/original.pdf")

    assert not path.exists()
    assert not path.parent.exists()


async def test_local_storage_delete_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage.settings, "storage_provider", "local")
    monkeypatch.setattr(storage.settings, "upload_dir", tmp_path)

    await storage.delete_pdf("documents/missing/original.pdf")
