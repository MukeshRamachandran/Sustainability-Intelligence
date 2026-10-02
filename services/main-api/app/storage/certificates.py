"""Dedicated storage for public certificate documents.

Certificates have their own storage root and lifecycle; they never share the
evidence volumes or the database. A stored file is addressed only by an opaque
key generated here - the uploaded filename is kept as metadata and is never
used as a path. The file-type rules (declared type, extension and leading
signature must all agree) are the ones evidence uploads already use.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import Settings
from app.storage.evidence import CHUNK_SIZE, TYPE_RULES, safe_original_filename

STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.(?:pdf|png|jpg)$")
ALLOWED_CERTIFICATE_TYPES = ("image/jpeg", "image/png", "application/pdf")


@dataclass(frozen=True)
class StoredCertificateFile:
    storage_key: str
    original_filename: str
    mime_type: str
    byte_size: int
    sha256: str
    path: Path


def certificate_directory(settings: Settings) -> Path:
    return settings.CERTIFICATE_STORAGE_ROOT


def certificate_path(settings: Settings, storage_key: str) -> Path:
    """The file for a storage key, or a 500 if the key could leave the storage root."""
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise HTTPException(status_code=500, detail="Stored certificate reference is invalid.")
    root = certificate_directory(settings).resolve()
    path = (root / storage_key).resolve()
    if path.parent != root:
        raise HTTPException(status_code=500, detail="Stored certificate reference is invalid.")
    return path


async def store_certificate_upload(upload: UploadFile, settings: Settings) -> StoredCertificateFile:
    original_filename = safe_original_filename(upload.filename)
    extension = Path(original_filename).suffix.casefold()
    declared_type = (upload.content_type or "").casefold()
    if declared_type not in ALLOWED_CERTIFICATE_TYPES:
        raise HTTPException(status_code=422, detail="PDF, PNG and JPG files only.")
    allowed_extensions, signature, stored_extension = TYPE_RULES[declared_type]
    if extension not in allowed_extensions:
        raise HTTPException(status_code=422, detail="The filename extension does not match an allowed document type.")

    root = certificate_directory(settings)
    root.mkdir(parents=True, exist_ok=True)
    identifier = uuid4().hex
    temporary_path = root / f".{identifier}.part"
    final_key = f"{identifier}.{stored_extension}"
    final_path = certificate_path(settings, final_key)
    digest = hashlib.sha256()
    size = 0
    leading = b""
    try:
        with temporary_path.open("xb") as target:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Maximum certificate file size is 10 MB.")
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

    return StoredCertificateFile(
        storage_key=final_key,
        original_filename=original_filename,
        mime_type=declared_type,
        byte_size=size,
        sha256=digest.hexdigest(),
        path=final_path,
    )


def remove_new_certificate_file(path: Path) -> None:
    path.unlink(missing_ok=True)
