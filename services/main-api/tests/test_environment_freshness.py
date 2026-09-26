from datetime import UTC, datetime, timedelta

import pytest

from app.environment.freshness import classify_freshness

NOW = datetime(2026, 9, 25, 3, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(0), "LIVE"),
        (timedelta(minutes=9, seconds=59), "LIVE"),
        (timedelta(minutes=10), "STALE"),
        (timedelta(minutes=30), "STALE"),
        (timedelta(minutes=30, seconds=1), "OFFLINE"),
        (timedelta(hours=4, minutes=56), "OFFLINE"),
        (timedelta(minutes=-1), "LIVE"),
        (timedelta(minutes=-3), "OFFLINE"),
    ],
)
def test_freshness_boundaries(age: timedelta, expected: str) -> None:
    assert classify_freshness(NOW - age, NOW) == expected


def test_missing_reading_is_offline() -> None:
    assert classify_freshness(None, NOW) == "OFFLINE"


def test_naive_database_timestamps_are_treated_as_utc() -> None:
    assert classify_freshness(datetime(2026, 9, 25, 3, 25), NOW) == "LIVE"


def test_the_legacy_330_shift_would_make_the_real_reading_future_dated() -> None:
    observed = datetime(2026, 9, 24, 22, 34, tzinfo=UTC)
    fetched = datetime(2026, 9, 25, 3, 18, 51, tzinfo=UTC)
    assert classify_freshness(observed, fetched) == "OFFLINE"
    assert observed + timedelta(minutes=330) > fetched
