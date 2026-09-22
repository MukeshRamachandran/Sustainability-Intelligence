from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_comma_separated_origins_are_validated(tmp_path: Path) -> None:
    settings = Settings(
        APP_ENV="test",
        ALLOWED_ORIGINS="http://localhost:3000,https://portal.example.edu",
        EVIDENCE_ROOT=tmp_path,
    )
    assert settings.ALLOWED_ORIGINS == ["http://localhost:3000", "https://portal.example.edu"]


@pytest.mark.parametrize("origin", ["*", "file:///tmp/site", "https://example.edu/path"])
def test_unsafe_origins_are_rejected(origin: str, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(APP_ENV="test", ALLOWED_ORIGINS=[origin], EVIDENCE_ROOT=tmp_path)


def test_production_rejects_development_defaults(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            PUBLIC_BASE_URL="https://sustainability.example.edu",
            EVIDENCE_ROOT=tmp_path.resolve(),
            SESSION_COOKIE_SECURE=True,
        )


def test_production_accepts_replaced_security_values(tmp_path: Path) -> None:
    settings = Settings(
        APP_ENV="production",
        DATABASE_URL="postgresql+psycopg://app:unique-password@db.internal/microcosm",
        PUBLIC_BASE_URL="https://sustainability.example.edu",
        ALLOWED_ORIGINS=["https://sustainability.example.edu"],
        SECRET_KEY="s" * 48,
        CSRF_SECRET="c" * 48,
        SESSION_COOKIE_SECURE=True,
        EVIDENCE_ROOT=tmp_path.resolve(),
    )
    assert settings.APP_ENV == "production"
