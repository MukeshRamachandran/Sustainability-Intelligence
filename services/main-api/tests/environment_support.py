import copy
import json
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from app.models.environment import EnvironmentIngestionRun, EnvironmentReading

FIXTURES = Path(__file__).parent / "fixtures" / "aeron"
# Retired cookie-authenticated route (2026-09-25); kept as timestamp evidence.
LEGACY_FIXTURE = FIXTURES / "aeron_real_sample_sanitized.json"
# REST API v1 with Bearer key (2026-11-02).
V1_FIXTURE = FIXTURES / "aeron_v1_sample_sanitized.json"


@cache
def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def legacy_fixture() -> dict[str, Any]:
    return copy.deepcopy(_load(LEGACY_FIXTURE))


def v1_fixture() -> dict[str, Any]:
    return copy.deepcopy(_load(V1_FIXTURE))


def real_timeseries_payload() -> dict[str, Any]:
    payload: dict[str, Any] = v1_fixture()["timeseries_latest"]
    return payload


def timeseries_payload_at(observed_at: datetime, **values: float | None) -> dict[str, Any]:
    """The real v1 payload moved to another instant, with selected values replaced by parameter ID."""
    payload = real_timeseries_payload()
    payload["reading"]["timestamp"] = observed_at.isoformat().replace("+00:00", "Z")
    payload["reading"]["epoch_ms"] = int(observed_at.timestamp() * 1000)
    payload["reading"]["values"].update(values)
    return payload


def real_station_id() -> str:
    return str(_load(V1_FIXTURE)["_provenance"]["station_id"])


def environment_sqlite_engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"environment": None}},
    )
    EnvironmentReading.__table__.create(engine)
    EnvironmentIngestionRun.__table__.create(engine)
    return engine
