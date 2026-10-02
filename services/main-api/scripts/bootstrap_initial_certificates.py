"""One-time idempotent bootstrap for the two owner-approved 2025 E-Waste
certificates. Future certificates must be created through Admin.

INITIAL DATA SEED ONLY (project-owner instruction, 2026-10-02). The normal way
to add a certificate is Admin -> Certificates -> Upload Certificate; this
script exists only because the first two documents were supplied as sideways
photographs and are loaded once, as upright landscape copies.

Two stages, because rotating an image needs an imaging library that the API
runtime deliberately does not carry:

  prepare   Runs on a workstation that has Pillow (BOOTSTRAP TOOLING ONLY - it
            is not, and must not become, an API dependency). Verifies the two
            ORIGINAL files by SHA-256, never modifies them, and writes upright
            landscape JPEG copies plus a manifest into a work directory.

  load      Runs in the API environment (no Pillow needed). Registers each
            landscape copy through the application's own certificate code -
            the same upload, validation, storage, audit and publish functions
            the Admin endpoints run - then publishes it. No SQL is written
            here and no file is copied into storage by hand.

Safe to re-run: a certificate that already exists (same stored file hash, or
same domain + reporting year + serial number) is never created twice. If an
existing record's metadata differs from what is listed here the script stops
without changing anything.

    python scripts/bootstrap_initial_certificates.py prepare --source-dir <originals> --work-dir <work>
    python scripts/bootstrap_initial_certificates.py load --work-dir <work>

Certificates are supporting documents. Their quantity is document metadata and
is not used by any waste or other sustainability calculation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

MANIFEST = "manifest.json"
# Verified by eye on the generated copies: a quarter turn anticlockwise makes the
# header read left-to-right with CPCB / TNPCB at the upper left.
ROTATION = "90 degrees anticlockwise"
JPEG_QUALITY = 95
COMMON: dict[str, Any] = {
    "domain": "waste",
    "certificate_type": "E-Waste Disposal Certificate",
    "reporting_year": 2025,  # the disposal dates are in November 2025; not derived from the issue date
    "issuer": "Green India Recyclers",
    "registration_id": "1718109",
    "authorization_no": "20HFZ8007031",
    "certificate_date": date(2026, 1, 23),
    "quantity_unit": "kg",
}
CERTIFICATES: list[dict[str, Any]] = [
    {
        "source_file": "e-waste-2025-11-28-1640kg.jpeg.jpeg",
        "source_sha256": "8f5d57881fc0064a731b4dc7f1a1e2e8c25476f604698c9311da44fb55bd28f4",
        "derived_file": "ewaste-2025-11-28-landscape.jpg",
        "fields": {
            **COMMON,
            "title": "E-Waste Disposal Certificate — 28 Nov 2025",
            "received_date": date(2025, 11, 28),
            "quantity_value": Decimal("1640"),
            "invoice_no": "KCT/25-26/GST/468, 469 and 470",
            "manifest_doc_no": "GIR/746/2025-26",
            "serial_no": "2041-1",
            "display_order": 0,
        },
    },
    {
        "source_file": "e-waste-2025-11-29-1390kg.jpeg.jpeg",
        "source_sha256": "1adabc916f2752a558f2b16e3d4220d5e5ff3aeb1d9ac3786e779a18f67921da",
        "derived_file": "ewaste-2025-11-29-landscape.jpg",
        "fields": {
            **COMMON,
            "title": "E-Waste Disposal Certificate — 29 Nov 2025",
            "received_date": date(2025, 11, 29),
            "quantity_value": Decimal("1390"),
            "invoice_no": "KCT/25-26/GST/471",
            "manifest_doc_no": "GIR/747/2025-26",
            "serial_no": "2041-2",
            "display_order": 1,
        },
    },
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stop(message: str) -> None:
    print(f"STOP: {message}")
    raise SystemExit(2)


def note_for(item: dict[str, Any]) -> str:
    """Internal provenance note (never returned by the public API)."""
    return (
        "Loaded by the one-time bootstrap script on the project owner's instruction (2026-10-02). "
        "Landscape display copy derived from the original source photograph. "
        f"Original source SHA256: {item['source_sha256']}. "
        f"Transformation: rotation by {ROTATION} and JPEG re-encoding at quality {JPEG_QUALITY}; no content edit."
    )


# ---- Stage 1: prepare (workstation, Pillow) ------------------------------------------


def prepare(source_dir: Path, work_dir: Path) -> None:
    try:
        from PIL import Image, ImageOps  # bootstrap tooling only; not an API dependency
    except ImportError:
        stop("Pillow is required for the prepare stage (bootstrap tooling only; do not add it to the API).")
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for item in CERTIFICATES:
        source = source_dir / item["source_file"]
        if not source.is_file():
            stop(f"original not found: {source}")
        original = source.read_bytes()  # read only; the original is never written
        if sha256(original) != item["source_sha256"]:
            stop(f"original hash differs for {source.name}: {sha256(original)}")
        with Image.open(BytesIO(original)) as image:
            upright = ImageOps.exif_transpose(image).transpose(Image.Transpose.ROTATE_90)
            if upright.width <= upright.height:
                stop(f"{source.name}: the rotated copy is not landscape ({upright.width}x{upright.height})")
            buffer = BytesIO()
            upright.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            original_size = image.size
        derived = buffer.getvalue()
        (work_dir / item["derived_file"]).write_bytes(derived)
        manifest.append(
            {
                "source_file": item["source_file"],
                "source_sha256": item["source_sha256"],
                "source_dimensions": list(original_size),
                "derived_file": item["derived_file"],
                "derived_sha256": sha256(derived),
                "derived_dimensions": [upright.width, upright.height],
                "derived_bytes": len(derived),
                "rotation": ROTATION,
            }
        )
        print(
            f"PREPARED {item['derived_file']}: {original_size[0]}x{original_size[1]} -> "
            f"{upright.width}x{upright.height}, {len(derived)} bytes, sha256 {sha256(derived)}"
        )
        if sha256(source.read_bytes()) != item["source_sha256"]:
            stop(f"original changed during preparation: {source}")
    (work_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---- Stage 2: load (API environment; the application's own certificate code) ----------


def _matches(certificate: Any, fields: dict[str, Any], derived_sha256: str) -> list[str]:
    """Names of the fields in which an existing record differs from this script."""
    differing = [name for name, value in fields.items() if getattr(certificate, name) != value]
    if certificate.sha256 != derived_sha256:
        differing.append("sha256")
    return differing


async def load(work_dir: Path) -> None:
    from sqlalchemy import or_, select
    from starlette.datastructures import Headers, UploadFile
    from starlette.requests import Request

    from app.core.config import get_settings
    from app.main import create_app
    from app.models.enums import RoleCode
    from app.models.publication import Certificate
    from app.routers.certificates import publish_certificate, upload_certificate
    from app.security.dependencies import AuthContext
    from app.storage.certificates import certificate_path

    manifest_path = work_dir / MANIFEST
    if not manifest_path.is_file():
        stop(f"manifest not found: {manifest_path} (run the prepare stage first)")
    manifest = {entry["derived_file"]: entry for entry in json.loads(manifest_path.read_text(encoding="utf-8"))}

    settings = get_settings()
    application = create_app(settings)
    settings.CERTIFICATE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    request = Request(
        {
            "type": "http", "method": "POST", "path": "/bootstrap/initial-certificates", "headers": [],
            "query_string": b"", "app": application, "state": {"request_id": str(uuid4())},
        }
    )
    # No person performed this load, so no user is named: the records carry no
    # creator and the audit rows no actor. The notes state how they were loaded.
    system = AuthContext(
        user_id=None,  # type: ignore[arg-type]
        session_id=uuid4(),
        username="bootstrap",
        display_name="Initial certificate bootstrap",
        role=RoleCode.ADMIN,
        manager_domain=None,
        must_change_password=False,
    )
    results = []
    try:
        with application.state.session_factory() as db:
            for item in CERTIFICATES:
                fields: dict[str, Any] = item["fields"]
                entry = manifest.get(item["derived_file"])
                derived_path = work_dir / item["derived_file"]
                if entry is None or not derived_path.is_file():
                    stop(f"derived copy missing: {derived_path}")
                derived = derived_path.read_bytes()
                if entry["source_sha256"] != item["source_sha256"] or sha256(derived) != entry["derived_sha256"]:
                    stop(f"{item['derived_file']} does not match its manifest; run the prepare stage again")

                existing = db.scalars(
                    select(Certificate).where(
                        or_(
                            Certificate.sha256 == sha256(derived),
                            (Certificate.domain == fields["domain"])
                            & (Certificate.reporting_year == fields["reporting_year"])
                            & (Certificate.serial_no == fields["serial_no"]),
                        )
                    )
                ).all()
                if len(existing) > 1:
                    stop(f"{fields['serial_no']}: more than one existing record matches; resolve in Admin")
                if existing:
                    certificate = existing[0]
                    differing = _matches(certificate, fields, sha256(derived))
                    if differing:
                        stop(f"{fields['serial_no']}: existing record {certificate.id} differs in {differing}")
                    if certificate.status == "DRAFT":
                        certificate = publish_certificate(certificate.id, request, system, db)
                        outcome = "ALREADY EXISTS (draft) - published"
                    else:
                        outcome = f"ALREADY EXISTS ({certificate.status}) - left unchanged"
                else:
                    upload = UploadFile(
                        file=BytesIO(derived), filename=item["derived_file"],
                        headers=Headers({"content-type": "image/jpeg"}),
                    )
                    certificate = await upload_certificate(
                        request, system, db, upload, notes=note_for(item), **fields
                    )
                    if certificate.status != "DRAFT" or _matches(certificate, fields, sha256(derived)):
                        stop(f"{fields['serial_no']}: the stored draft does not match; nothing was published")
                    stored = certificate_path(settings, certificate.storage_key)
                    if not stored.is_file() or sha256(stored.read_bytes()) != sha256(derived):
                        stop(f"{fields['serial_no']}: the stored file does not match the landscape copy")
                    certificate = publish_certificate(certificate.id, request, system, db)
                    outcome = "CREATED and PUBLISHED"
                stored = certificate_path(settings, certificate.storage_key)
                results.append(
                    {
                        "outcome": outcome, "id": str(certificate.id), "status": certificate.status,
                        "title": certificate.title, "serial_no": certificate.serial_no,
                        "manifest_doc_no": certificate.manifest_doc_no,
                        "quantity": f"{certificate.quantity_value.normalize():f} {certificate.quantity_unit}",
                        "stored_sha256": certificate.sha256, "original_sha256": item["source_sha256"],
                        "stored_file_valid": stored.is_file() and sha256(stored.read_bytes()) == certificate.sha256,
                        "byte_size": certificate.byte_size,
                    }
                )
    finally:
        application.state.engine.dispose()
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    if not all(result["stored_file_valid"] for result in results):
        stop("a stored file is missing or does not match its recorded hash")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    stages = parser.add_subparsers(dest="stage", required=True)
    prepare_parser = stages.add_parser("prepare", help="verify the originals and write landscape copies (needs Pillow)")
    prepare_parser.add_argument("--source-dir", required=True, type=Path)
    prepare_parser.add_argument("--work-dir", required=True, type=Path)
    load_parser = stages.add_parser("load", help="register and publish the landscape copies (API environment)")
    load_parser.add_argument("--work-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)
    if arguments.stage == "prepare":
        prepare(arguments.source_dir, arguments.work_dir)
    else:
        asyncio.run(load(arguments.work_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
