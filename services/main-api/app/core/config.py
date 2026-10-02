from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEVELOPMENT_SECRETS = {
    "development-only-change-me",
    "development-csrf-change-me",
    "change-me",
    "secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str = "postgresql+psycopg://microcosm_app:microcosm_dev_only@localhost:5432/microcosm"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    INSTITUTION_TIMEZONE: str = "Asia/Kolkata"
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    SECRET_KEY: str = "development-only-change-me"  # noqa: S105 -- rejected in production
    CSRF_SECRET: str = "development-csrf-change-me"  # noqa: S105 -- rejected in production
    SESSION_COOKIE_NAME: str = "microcosm_session"
    CSRF_COOKIE_NAME: str = "microcosm_csrf"
    SESSION_IDLE_MINUTES: int = Field(default=60, ge=5, le=1440)
    SESSION_ABSOLUTE_HOURS: int = Field(default=8, ge=1, le=168)
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict"] = "lax"
    EVIDENCE_ROOT: Path = Path(".local/evidence")
    MAX_UPLOAD_BYTES: int = Field(default=10_485_760, ge=1, le=10_485_760)
    EVIDENCE_STORAGE_DIR: Path | None = None
    MAX_EVIDENCE_FILE_SIZE_BYTES: int = Field(default=10_485_760, ge=1, le=10_485_760)
    ALLOWED_EVIDENCE_TYPES: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["application/pdf", "image/png", "image/jpeg"]
    )
    # Public certificate documents: their own root, never the evidence volumes or the database.
    CERTIFICATE_STORAGE_ROOT: Path = Path(".local/certificates")
    LOGIN_MAX_FAILURES: int = Field(default=5, ge=3, le=20)
    LOGIN_LOCK_MINUTES: int = Field(default=15, ge=1, le=1440)
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=12, le=128)

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("at least one allowed origin is required")
        for origin in origins:
            parsed = urlparse(origin)
            if origin == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("allowed origins must be explicit HTTP(S) origins")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("allowed origins cannot contain paths, queries, or fragments")
        return list(dict.fromkeys(origin.rstrip("/") for origin in origins))

    @field_validator("INSTITUTION_TIMEZONE")
    @classmethod
    def validate_institution_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("institution timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("ALLOWED_EVIDENCE_TYPES", mode="before")
    @classmethod
    def parse_evidence_types(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("ALLOWED_EVIDENCE_TYPES")
    @classmethod
    def validate_evidence_types(cls, values: list[str]) -> list[str]:
        allowed = {"application/pdf", "image/png", "image/jpeg"}
        if not values or not set(values).issubset(allowed):
            raise ValueError("evidence types must be PDF, PNG, or JPEG")
        return list(dict.fromkeys(values))

    @field_validator("EVIDENCE_ROOT")
    @classmethod
    def validate_evidence_root(cls, path: Path) -> Path:
        if not str(path).strip() or ".." in path.parts:
            raise ValueError("evidence root must be a safe configured directory")
        return path

    @field_validator("EVIDENCE_STORAGE_DIR")
    @classmethod
    def validate_evidence_storage_dir(cls, path: Path | None) -> Path | None:
        if path is not None and (not str(path).strip() or ".." in path.parts):
            raise ValueError("evidence storage directory must be a safe configured directory")
        return path

    @model_validator(mode="after")
    def validate_environment_security(self) -> Settings:
        if self.APP_ENV == "production":
            if self.SECRET_KEY in DEVELOPMENT_SECRETS or len(self.SECRET_KEY) < 32:
                raise ValueError("production SECRET_KEY must be replaced")
            if self.CSRF_SECRET in DEVELOPMENT_SECRETS or len(self.CSRF_SECRET) < 32:
                raise ValueError("production CSRF_SECRET must be replaced")
            if not self.SESSION_COOKIE_SECURE:
                raise ValueError("production session cookies must be secure")
            if urlparse(self.PUBLIC_BASE_URL).scheme != "https":
                raise ValueError("production public base URL must use HTTPS")
            if "microcosm_dev_only" in self.DATABASE_URL:
                raise ValueError("development database credentials are forbidden in production")
            if not self.EVIDENCE_ROOT.is_absolute():
                raise ValueError("production evidence root must be absolute")
            if self.EVIDENCE_STORAGE_DIR is not None and not self.EVIDENCE_STORAGE_DIR.is_absolute():
                raise ValueError("production evidence storage directory must be absolute")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
