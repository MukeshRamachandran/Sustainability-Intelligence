from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.environment.normalizer import InvalidReadingError, normalize_reading, parse_observed_at
from app.environment.parameters import AERON_PARAMETERS, METRIC_FIELDS
from tests.environment_support import real_fixture, real_latest_payload, real_station_id


def test_real_latest_payload_normalizes_every_verified_metric() -> None:
    reading = normalize_reading(real_latest_payload(), real_station_id())

    assert reading.station_id == real_station_id()
    assert reading.observed_at == datetime(2026, 9, 24, 22, 34, tzinfo=UTC)
    assert reading.source_recorded_at_raw == "2026-09-24T22:34:00.000Z"
    assert set(reading.metrics) == set(METRIC_FIELDS)
    assert reading.metrics["temperature_c"] == pytest.approx(27.113262)
    assert reading.metrics["relative_humidity_percent"] == pytest.approx(69.387342)
    assert reading.metrics["pm25_ug_m3"] == pytest.approx(4.693056)
    assert reading.metrics["no_ug_m3"] == pytest.approx(0.000789)  # not truncated
    assert reading.metrics["rain_mm"] == 0.0  # a real zero is kept, not treated as missing
    assert reading.metrics["air_quality_index"] == 107.0
    assert reading.health == {"network": 4, "battery": 0, "charging": 0, "device_temp": 0}
    assert reading.quality_flags == []


def test_real_parameter_metadata_matches_the_verified_map() -> None:
    source = {item["id"]: item for item in real_fixture()["parameters"]["body"]}
    assert set(source) == set(AERON_PARAMETERS)
    for parameter_id, parameter in AERON_PARAMETERS.items():
        assert source[parameter_id]["caption"] == parameter.caption
        assert source[parameter_id]["unit"] == parameter.source_unit


def test_both_verified_timestamp_formats_are_the_same_utc_instant() -> None:
    latest = parse_observed_at("2026-09-24T22:34:00.000Z")
    history = parse_observed_at("2026-09-24 22:34:00+00")
    assert latest == history == datetime(2026, 9, 24, 22, 34, tzinfo=UTC)


def test_no_330_minute_correction_is_applied() -> None:
    # Worked example from live verification: Aeron's dashboard showed this
    # reading as "4 hrs ago" at 03:25Z, and the source received it at 22:34:14Z.
    observed = parse_observed_at("2026-09-24T22:34:00.000Z")
    received = parse_observed_at(real_fixture()["health"]["body"]["receivedAt"])

    assert observed.astimezone(ZoneInfo("Asia/Kolkata")).isoformat() == "2026-09-25T04:04:00+05:30"
    assert 0 <= (received - observed).total_seconds() < 60


def test_real_history_rows_normalize_and_advance() -> None:
    rows = real_fixture()["history_excerpt"]["rows"]
    readings = [normalize_reading(row, real_station_id()) for row in rows]
    times = [reading.observed_at for reading in readings]
    assert times == sorted(times) and len(set(times)) == len(times)


@pytest.mark.parametrize(
    "value",
    [None, "", "yesterday", "2026-09-24T22:34:00", 1727217240, "2026-13-01T00:00:00Z"],
)
def test_invalid_or_naive_timestamps_are_rejected(value: object) -> None:
    payload = real_latest_payload()
    payload["recordedAt"] = value
    with pytest.raises(InvalidReadingError):
        normalize_reading(payload, "station")


def test_non_utc_offsets_are_converted_to_utc() -> None:
    assert parse_observed_at("2026-09-25T04:04:00+05:30") == datetime(2026, 9, 24, 22, 34, tzinfo=UTC)


@pytest.mark.parametrize("payload", [None, {}, [], "text", {"recordedAt": "2026-09-24T22:34:00Z"}])
def test_malformed_payloads_are_rejected(payload: object) -> None:
    with pytest.raises(InvalidReadingError):
        normalize_reading(payload, "station")


def test_missing_null_and_non_numeric_metrics_become_null_with_flags() -> None:
    payload = real_latest_payload()
    del payload["data"]["63d0dbfe0a111"]
    payload["data"]["63d0dc28f109d"] = None
    payload["data"]["63d0db8f77ecb"] = "n/a"
    payload["data"]["63d0dbb867a7c"] = True
    payload["data"]["new-sensor"] = 1.5

    reading = normalize_reading(payload, "station")

    assert reading.metrics["temperature_c"] is None
    assert reading.metrics["relative_humidity_percent"] is None
    assert reading.metrics["pm25_ug_m3"] is None
    assert reading.metrics["pm10_ug_m3"] is None
    assert "missing:temperature_c" in reading.quality_flags
    assert "non_numeric:pm25_ug_m3" in reading.quality_flags
    assert "non_numeric:pm10_ug_m3" in reading.quality_flags
    assert "unknown_parameter:new-sensor" in reading.quality_flags
    assert "relative_humidity_percent" not in " ".join(reading.quality_flags)
    assert reading.raw_payload["data"]["new-sensor"] == 1.5


def test_reading_without_any_numeric_metric_is_rejected() -> None:
    payload = real_latest_payload()
    payload["data"] = {key: None for key in payload["data"]}
    with pytest.raises(InvalidReadingError):
        normalize_reading(payload, "station")
