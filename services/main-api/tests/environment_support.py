import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from app.models.environment import EnvironmentIngestionRun, EnvironmentReading

FIXTURE = Path(__file__).parent / "fixtures" / "aeron" / "aeron_real_sample_sanitized.json"


@cache
def _fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def real_fixture() -> dict[str, Any]:
    return copy.deepcopy(_fixture())


def real_latest_payload() -> dict[str, Any]:
    payload: dict[str, Any] = real_fixture()["latest"]["body"]
    return payload


def real_station_id() -> str:
    return str(_fixture()["_provenance"]["station_id"])


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
