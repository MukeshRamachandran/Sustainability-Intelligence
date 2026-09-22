from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.database.models import AeronMeasurement, AeronStation, Base
from backend.services import aeron_sync_service


class FakeClient:
    internal_base_url = "https://fallback.invalid"

    def __init__(self, fail_public: bool = False) -> None:
        self.fail_public = fail_public
        self.fallback_calls = 0

    def payload(self) -> dict[str, object]:
        return {
            "recordedAt": "2026-09-19T10:00:00Z",
            "health": {"network": 4, "battery": 90, "charging": 1, "DeviceTemp": 32},
            "data": {"63d0da020016a": 0.5, "63d0db8f77ecb": 15.2},
        }

    def get_latest_reading(self, _station_id: str) -> dict[str, object]:
        if self.fail_public:
            raise ValueError("public unavailable")
        return self.payload()

    def get_latest_reading_internal(self, _station_id: str) -> dict[str, object]:
        self.fallback_calls += 1
        return self.payload()


class FailingClient(FakeClient):
    def __init__(self) -> None:
        super().__init__(fail_public=True)

    def get_latest_reading_internal(self, _station_id: str) -> dict[str, object]:
        self.fallback_calls += 1
        raise ValueError("upstream-cookie=must-not-leak")


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"environmental": None}},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_sync_inserts_raw_payload_and_prevents_duplicates(db_session, monkeypatch):
    monkeypatch.setattr(aeron_sync_service, "aeron_client", FakeClient())
    monkeypatch.setattr(settings, "aeron_retry_count", 1)
    monkeypatch.setattr(settings, "aeron_timestamp_correction_minutes", 0)

    first = aeron_sync_service.sync_aeron_station(db_session, "TEST-STATION")
    second = aeron_sync_service.sync_aeron_station(db_session, "TEST-STATION")

    assert first.status == "SUCCESS" and first.records_inserted == 1
    assert second.status == "SUCCESS" and second.records_skipped == 1
    assert db_session.query(AeronStation).count() == 1
    assert db_session.query(AeronMeasurement).count() == 1
    measurement = db_session.query(AeronMeasurement).one()
    assert measurement.raw_payload["data"]["63d0da020016a"] == 0.5
    assert measurement.source_recorded_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 9, 19, 10, 0, tzinfo=timezone.utc
    )


def test_public_failure_uses_configured_fallback(db_session, monkeypatch):
    client = FakeClient(fail_public=True)
    monkeypatch.setattr(aeron_sync_service, "aeron_client", client)
    monkeypatch.setattr(settings, "aeron_fallback_enabled", True)
    monkeypatch.setattr(settings, "aeron_retry_count", 1)
    monkeypatch.setattr(settings, "aeron_timestamp_correction_minutes", 0)

    result = aeron_sync_service.sync_aeron_station(db_session, "TEST-STATION")

    assert result.status == "SUCCESS"
    assert client.fallback_calls == 1


def test_total_upstream_failure_is_recorded_without_secret_details(db_session, monkeypatch):
    monkeypatch.setattr(aeron_sync_service, "aeron_client", FailingClient())
    monkeypatch.setattr(settings, "aeron_fallback_enabled", True)
    monkeypatch.setattr(settings, "aeron_retry_count", 1)

    result = aeron_sync_service.sync_aeron_station(db_session, "TEST-STATION")

    assert result.status == "FAILED"
    assert result.error_message == "Failed after 1 attempts (ValueError)."
    assert "cookie" not in result.error_message
