from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.environment.normalizer import (
    InvalidReadingError,
    StationMismatchError,
    normalize_timeseries,
    parse_observed_at,
)
from app.environment.parameters import AERON_PARAMETERS, METRIC_FIELDS, PARAMETER_MAP, READING_COLUMNS
from tests.environment_support import legacy_fixture, real_station_id, real_timeseries_payload, v1_fixture

STATION = real_station_id()
OBSERVED = datetime(2026, 11, 2, 10, 58, 1, tzinfo=UTC)


def test_real_v1_payload_normalizes_every_mapped_metric() -> None:
    reading = normalize_timeseries(real_timeseries_payload(), STATION)

    assert reading.station_id == STATION
    assert reading.observed_at == OBSERVED
    assert reading.source_recorded_at_raw == "2026-11-02T10:58:01.000Z"
    assert reading.source_epoch_ms == 1793617081000
    assert set(reading.metrics) == set(METRIC_FIELDS)
    assert reading.metrics["air_quality_index"] == 107.0
    assert reading.metrics["pm25_ug_m3"] == pytest.approx(44.372241)
    assert reading.metrics["pm10_ug_m3"] == pytest.approx(67.605019)
    assert reading.metrics["co2_ppm"] == pytest.approx(380.414971)
    assert reading.metrics["temperature_c"] == pytest.approx(33.312846)
    assert reading.metrics["relative_humidity_percent"] == pytest.approx(59.291974)
    assert reading.metrics["barometric_pressure_mba"] == 150.0  # stored as sent, not "corrected"
    assert reading.metrics["rain_mm"] == 0.0  # a real zero is kept, not treated as missing
    assert reading.metrics["wind_speed_kmph"] == 0.0
    assert reading.unmapped_values == {}
    assert reading.quality_flags == []
    assert reading.raw_payload["reading"]["values"]["6422ae0f8147e"] == 107


def test_parameter_map_has_the_35_owner_supplied_ids_bound_to_existing_columns() -> None:
    assert len(PARAMETER_MAP) == 35
    assert set(PARAMETER_MAP) == set(READING_COLUMNS) == set(AERON_PARAMETERS)
    assert len(set(READING_COLUMNS.values())) == 35
    assert {meta["category"] for meta in PARAMETER_MAP.values()} == {
        "air_quality",
        "weather",
        "noise",
        "diagnostics",
        "pollutant_ppb",
    }
    assert AERON_PARAMETERS["6422ae0f8147e"].field == "air_quality_index"
    assert AERON_PARAMETERS["63d0db8f77ecb"].name == "PM2.5"


def test_live_parameter_metadata_matches_the_map_except_the_documented_aqi_unit() -> None:
    source = {item["code"]: item["unit"] for item in v1_fixture()["parameters"]["parameters"]}
    assert set(source) == set(PARAMETER_MAP)
    differing = {code for code, meta in PARAMETER_MAP.items() if source[code] != meta["unit"]}
    assert differing == {"6422ae0f8147e"}  # Aeron says "Unit"; the owner map says "index"
    assert AERON_PARAMETERS["6422ae0f8147e"].note is not None


def test_every_live_value_id_is_mapped() -> None:
    assert set(real_timeseries_payload()["reading"]["values"]) == set(PARAMETER_MAP)


def test_timestamp_is_utc_and_displays_in_ist_without_double_conversion() -> None:
    observed = parse_observed_at("2026-11-02T10:58:01.000Z")
    assert observed == OBSERVED
    assert observed.astimezone(ZoneInfo("Asia/Kolkata")).isoformat() == "2026-11-02T16:28:01+05:30"
    assert parse_observed_at("2026-11-02T16:28:01+05:30") == OBSERVED


def test_no_330_minute_correction_is_applied() -> None:
    # Legacy live evidence: Aeron received this reading 14 s after its timestamp.
    legacy = legacy_fixture()
    observed = parse_observed_at(legacy["latest"]["body"]["recordedAt"])
    received = parse_observed_at(legacy["health"]["body"]["receivedAt"])
    assert 0 <= (received - observed).total_seconds() < 60


@pytest.mark.parametrize(
    "value",
    [None, "", "yesterday", "2026-11-02T10:58:01", 1793617081000, "2026-13-01T00:00:00Z"],
)
def test_invalid_or_naive_timestamps_are_rejected(value: object) -> None:
    payload = real_timeseries_payload()
    payload["reading"]["timestamp"] = value
    with pytest.raises(InvalidReadingError):
        normalize_timeseries(payload, STATION)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        "text",
        {"station": STATION},
        {"station": STATION, "reading": {}},
        {"station": STATION, "reading": {"timestamp": "2026-11-02T10:58:01Z"}},
        {"station": STATION, "reading": {"timestamp": "2026-11-02T10:58:01Z", "values": []}},
    ],
)
def test_invalid_response_structures_are_rejected(payload: object) -> None:
    with pytest.raises(InvalidReadingError):
        normalize_timeseries(payload, STATION)


def test_reading_for_another_station_is_rejected() -> None:
    payload = real_timeseries_payload()
    payload["station"] = "someone-else"
    with pytest.raises(StationMismatchError):
        normalize_timeseries(payload, STATION)


def test_missing_null_and_non_numeric_values_become_null_never_zero() -> None:
    payload = real_timeseries_payload()
    values = payload["reading"]["values"]
    del values["63d0dbfe0a111"]
    values["63d0dc28f109d"] = None
    values["63d0db8f77ecb"] = "n/a"
    values["63d0dbb867a7c"] = True
    values["63d0ea1253e8f"] = float("nan")

    reading = normalize_timeseries(payload, STATION)

    for field in ("temperature_c", "relative_humidity_percent", "pm25_ug_m3", "pm10_ug_m3", "co2_ppm"):
        assert reading.metrics[field] is None
    assert "missing:temperature_c" in reading.quality_flags
    assert "non_numeric:pm25_ug_m3" in reading.quality_flags
    assert "non_numeric:pm10_ug_m3" in reading.quality_flags
    assert "relative_humidity_percent" not in " ".join(reading.quality_flags)  # explicit null is not "missing"


def test_unknown_parameter_ids_are_preserved_separately() -> None:
    payload = real_timeseries_payload()
    payload["reading"]["values"]["99aa00new0001"] = 1.5

    reading = normalize_timeseries(payload, STATION)

    assert reading.unmapped_values == {"99aa00new0001": 1.5}
    assert "unknown_parameter:99aa00new0001" in reading.quality_flags
    assert reading.raw_payload["reading"]["values"]["99aa00new0001"] == 1.5


def test_epoch_ms_is_optional_and_a_mismatch_is_flagged() -> None:
    payload = real_timeseries_payload()
    del payload["reading"]["epoch_ms"]
    assert normalize_timeseries(payload, STATION).source_epoch_ms is None

    payload = real_timeseries_payload()
    payload["reading"]["epoch_ms"] += 60_000
    assert "epoch_ms_mismatch" in normalize_timeseries(payload, STATION).quality_flags


def test_reading_without_any_numeric_metric_is_rejected() -> None:
    payload = real_timeseries_payload()
    payload["reading"]["values"] = {key: None for key in payload["reading"]["values"]}
    with pytest.raises(InvalidReadingError):
        normalize_timeseries(payload, STATION)
