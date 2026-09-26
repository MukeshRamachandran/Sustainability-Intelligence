"""Settings for the Aeron ingestion worker only.

The public API process never needs these. Credentials are read from the
process environment (never from a repository ``.env``) and held as
``SecretStr`` so they cannot leak through ``repr`` or logging.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AeronWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=True, extra="ignore")

    AERON_STATION_ID: str = Field(min_length=1, max_length=100)
    AERON_INTERNAL_BASE_URL: str = "https://live3.aeronsystems.com/api"
    # Entry point for login: it redirects to Aeron's Auth0 form with a fresh
    # ``state``. A stored Auth0 ``/u/login?state=...`` URL goes stale.
    AERON_DASHBOARD_URL: str = "https://live3.aeronsystems.com/dashboard"
    AERON_REGION: str = "india"
    AERON_USERNAME: SecretStr | None = None
    AERON_PASSWORD: SecretStr | None = None
    # Optional pre-existing session used before the first browser login.
    AERON_SESSION_COOKIE: SecretStr | None = None
    AERON_POLL_INTERVAL_SECONDS: int = Field(default=300, ge=60, le=3600)
    AERON_HTTP_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=120)
    AERON_LOGIN_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=180)

    @field_validator("AERON_INTERNAL_BASE_URL", "AERON_DASHBOARD_URL")
    @classmethod
    def require_https(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Aeron URLs must be plain HTTPS URLs without query strings")
        return value.rstrip("/")

    @property
    def login_configured(self) -> bool:
        return bool(
            self.AERON_USERNAME
            and self.AERON_USERNAME.get_secret_value()
            and self.AERON_PASSWORD
            and self.AERON_PASSWORD.get_secret_value()
        )
