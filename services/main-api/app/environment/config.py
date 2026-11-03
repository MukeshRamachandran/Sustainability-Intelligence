"""Settings for the Aeron ingestion worker only.

The public API process never needs these. Credentials come from the same
gitignored ``services/main-api/.env`` as the API and are held as ``SecretStr``
so they cannot leak through ``repr`` or logging.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import SERVICE_ENV_FILE

# Hard floor and ceiling for the poll interval: at most 720 requests/day (7% of
# Aeron's 10000) even if .env is misconfigured, and at least one poll per hour.
MIN_POLL_INTERVAL_SECONDS = 120
MAX_POLL_INTERVAL_SECONDS = 3600


class AeronWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVICE_ENV_FILE, case_sensitive=True, extra="ignore")

    AERON_STATION_ID: str = Field(min_length=1, max_length=100)
    AERON_API_BASE_URL: str = "https://live3.aeronsystems.com/api/v1"
    AERON_API_KEY: SecretStr | None = None
    # Aeron's /timeseries "latest" changes about every 7 minutes (measured 2026-11-03),
    # so polling every 5 minutes misses little and uses 288 of the 10000 daily requests.
    # Values outside the safe range are clamped, not rejected, so an old .env
    # (e.g. 60) can never stop the worker or exceed the floor.
    AERON_POLL_INTERVAL_SECONDS: int = 300
    AERON_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=60)
    AERON_READ_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=120)
    AERON_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=5)

    @field_validator("AERON_POLL_INTERVAL_SECONDS")
    @classmethod
    def clamp_poll_interval(cls, value: int) -> int:
        return min(max(value, MIN_POLL_INTERVAL_SECONDS), MAX_POLL_INTERVAL_SECONDS)

    @field_validator("AERON_API_BASE_URL")
    @classmethod
    def require_https(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("AERON_API_BASE_URL must be a plain HTTPS URL without a query string")
        return value.rstrip("/")

    @property
    def api_key_configured(self) -> bool:
        return bool(self.AERON_API_KEY and self.AERON_API_KEY.get_secret_value().strip())
