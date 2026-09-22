from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import Settings

CHUNK_SIZE = 1024 * 1024
STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.(?:pdf|png|jpg)$")
TYPE_RULES = {
    "application/pdf": ({".pdf"}, b"%PDF-", "pdf"),
    "image/png": ({".png"}, b"\x89PNG\r\n\x1a\n", "png"),
    "image/jpeg": ({".jpg", ".jpeg"}, b"\xff\xd8\xff", "jpg"),
}


@dataclass(frozen=True)
class StoredEvidenceFile:
    storage_key: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    path: Path


def evidence_directory(settings: Settings) -> Path:
    return settings.EVIDENCE_STORAGE_DIR or settings.EVIDENCE_ROOT / "clean"


def safe_original_filename(filename: str | None) -> str:
    normalized = (filename or "evidence").replace("\\", "/").split("/")[-1]
    normalized = normalized.replace("\r", "").replace("\n", "").replace("\x00", "").strip()
    return (normalized or "evidence")[:255]


def evidence_path(settings: Settings, storage_key: str) -> Path:
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise HTTPException(status_code=500, detail="Stored evidence reference is invalid.")
    root = evidence_directory(settings).resolve()
    path = (root / storage_key).resolve()
    if path.parent != root:
        raise HTTPException(status_code=500, detail="Stored evidence reference is invalid.")
    return path


async def store_upload(upload: UploadFile, settings: Settings) -> StoredEvidenceFile:
    original_filename = safe_original_filename(upload.filename)
    extension = Path(original_filename).suffix.casefold()
    declared_type = (upload.content_type or "").casefold()
    if declared_type not in settings.ALLOWED_EVIDENCE_TYPES or declared_type not in TYPE_RULES:
        raise HTTPException(status_code=422, detail="PDF, PNG and JPG files only.")
    allowed_extensions, signature, stored_extension = TYPE_RULES[declared_type]
    if extension not in allowed_extensions:
        raise HTTPException(status_code=422, detail="The filename extension does not match an allowed evidence type.")

    root = evidence_directory(settings)
    root.mkdir(parents=True, exist_ok=True)
    identifier = uuid4().hex
    temporary_path = root / f".{identifier}.part"
    final_key = f"{identifier}.{stored_extension}"
    final_path = evidence_path(settings, final_key)
    digest = hashlib.sha256()
    size = 0
    leading = b""
    try:
        with temporary_path.open("xb") as target:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.MAX_EVIDENCE_FILE_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="Maximum evidence file size is 10 MB.")
                if len(leading) < 16:
                    leading = (leading + chunk)[:16]
                digest.update(chunk)
                target.write(chunk)
        if size == 0 or not leading.startswith(signature):
            raise HTTPException(status_code=422, detail="File content does not match its declared PDF or image type.")
        temporary_path.replace(final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredEvidenceFile(
        storage_key=final_key,
        original_filename=original_filename,
        mime_type=declared_type,
        file_size_bytes=size,
        sha256=digest.hexdigest(),
        path=final_path,
    )


def remove_new_file(path: Path) -> None:
    path.unlink(missing_ok=True)
