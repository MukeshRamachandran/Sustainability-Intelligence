from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings, settings
from backend.database.connection import get_db
from backend.database.models import AeronMeasurement, AeronStation, Base
from backend.main import create_app
from backend.routes.environment import classify_freshness
from backend.routes import sync as sync_route
from backend.services import aeron_client as aeron_client_module


def test_postgresql_url_is_preserved_and_sqlite_is_not_silent():
    postgres = "postgresql://user:password@postgres:5432/microcosm"
    assert Settings(_env_file=None, database_url=postgres).resolved_database_url() == postgres
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, database_url="").resolved_database_url()
    with pytest.raises(RuntimeError):
        Settings(
            _env_file=None,
            app_env="production",
            aeron_allow_sqlite=False,
            database_url="sqlite:///unsafe.db",
        ).resolved_database_url()


def test_freshness_boundaries():
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    assert classify_freshness(now - timedelta(minutes=9, seconds=59), now) == "LIVE"
    assert classify_freshness(now - timedelta(minutes=10), now) == "STALE"
    assert classify_freshness(now - timedelta(minutes=30), now) == "STALE"
    assert classify_freshness(now - timedelta(minutes=30, seconds=1), now) == "OFFLINE"
    assert classify_freshness(None, now) == "OFFLINE"


@pytest.fixture
def api_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"environmental": None}},
    )
    Base.metadata.create_all(bind=engine)
    local_session = sessionmaker(bind=engine)
    with local_session() as db:
        station = AeronStation(aeron_station_id="KCT-1", name="KCT")
        db.add(station)
        db.add(
            AeronMeasurement(
                station_id="KCT-1",
                source_recorded_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
                recorded_at=datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc),
                temperature_c=27.5,
                raw_payload={"trace": "retained"},
            )
        )
        db.commit()

    app = create_app()

    def override_db():
        with local_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(settings, "aeron_internal_sync_token", "test-internal-token")
    client = TestClient(app)
    yield client
    client.close()
    Base.metadata.drop_all(bind=engine)


def test_latest_history_and_anonymous_sync_denied(api_client):
    live = api_client.get("/health/live")
    latest = api_client.get("/api/environment/latest")
    history = api_client.get("/api/environment/history?limit=10")
    denied = api_client.post("/api/environment/sync")

    assert live.status_code == 200 and live.json() == {"status": "live"}
    assert latest.status_code == 200
    assert latest.json()["temperature_c"] == 27.5
    assert history.status_code == 200 and len(history.json()) == 1
    assert denied.status_code == 403


def test_manual_sync_accepts_only_the_internal_token(api_client, monkeypatch):
    now = datetime.now(timezone.utc)
    result = SimpleNamespace(
        id=1,
        started_at=now,
        completed_at=now,
        status="SUCCESS",
        records_received=1,
        records_inserted=1,
        records_skipped=0,
        error_message=None,
    )
    monkeypatch.setattr(settings, "aeron_station_id", "KCT-1")
    monkeypatch.setattr(sync_route, "sync_aeron_station", lambda _db, _station: result)

    wrong = api_client.post(
        "/api/environment/sync", headers={"X-Internal-Sync-Token": "wrong"}
    )
    accepted = api_client.post(
        "/api/environment/sync", headers={"X-Internal-Sync-Token": "test-internal-token"}
    )

    assert wrong.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "SUCCESS"


def test_cors_uses_exact_origins_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "aeron_allowed_origins", "https://sustainability.kct.ac.in")

    app = create_app()
    cors = next(item for item in app.user_middleware if item.cls is CORSMiddleware)

    assert cors.kwargs["allow_origins"] == ["https://sustainability.kct.ac.in"]
    assert cors.kwargs["allow_credentials"] is False
    assert "*" not in cors.kwargs["allow_origins"]


def test_fallback_credential_is_not_returned_or_logged(monkeypatch, caplog):
    class ForbiddenResponse:
        status_code = 403

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class FakeHttpClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return ForbiddenResponse()

    secret = "private-session-cookie"
    monkeypatch.setattr(settings, "aeron_session_cookie", secret)
    monkeypatch.setattr(settings, "aeron_fallback_api_url", "https://fallback.invalid")
    monkeypatch.setattr(aeron_client_module.httpx, "Client", FakeHttpClient)
    client = aeron_client_module.AeronClient()

    with pytest.raises(ValueError, match="authorization failed") as error:
        client.get_latest_reading_internal("KCT-1")

    assert secret not in str(error.value)
    assert secret not in caplog.text


def test_frontend_uses_relative_environment_routes():
    root = Path(__file__).resolve().parents[2]
    weather_path = Path(os.environ.get("WEATHER_JS_PATH", root.parent / "weather.js"))
    weather = weather_path.read_text(encoding="utf-8")
    assert "const API_BASE = '/api/environment'" in weather
    assert "localhost:8000" not in weather
    assert "127.0.0.1:8000" not in weather
    assert "setInterval(tickLatest, POLL_MS)" in weather
    assert "if (document.body.dataset.page !== 'weather'" in weather
