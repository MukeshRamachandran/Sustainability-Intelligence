from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"

    aeron_api_key: str = ""
    aeron_public_api_url: str = ""
    aeron_base_url: str = ""  # Backward-compatible name.
    aeron_station_id: str = ""
    aeron_fallback_api_url: str = ""
    aeron_internal_base_url: str = ""  # Backward-compatible name.
    aeron_session_cookie: str = ""
    aeron_fallback_enabled: bool = True
    aeron_sync_enabled: bool = True
    aeron_sync_interval_seconds: int = 60
    aeron_request_timeout_seconds: float = 10.0
    aeron_retry_count: int = 3
    aeron_timestamp_correction_minutes: int = 330
    aeron_internal_sync_token: str = ""
    aeron_allowed_origins: str = ""

    database_url: str = ""
    aeron_allow_sqlite: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def public_api_url(self) -> str:
        return (self.aeron_public_api_url or self.aeron_base_url).rstrip("/")

    @property
    def fallback_api_url(self) -> str:
        return (self.aeron_fallback_api_url or self.aeron_internal_base_url).rstrip("/")

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.aeron_allowed_origins.split(",") if item.strip()]

    def resolved_database_url(self) -> str:
        value = self.database_url.strip()
        if not value:
            raise RuntimeError("DATABASE_URL is required; Aeron never silently falls back to SQLite.")
        if value.startswith("sqlite") and not (
            self.app_env in {"development", "test"} and self.aeron_allow_sqlite
        ):
            raise RuntimeError("SQLite requires AERON_ALLOW_SQLITE=true in development or test only.")
        return value


settings = Settings()
