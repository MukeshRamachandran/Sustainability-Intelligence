"""Central freshness classification, always computed from server time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

Freshness = Literal["LIVE", "STALE", "OFFLINE"]

LIVE_BEFORE = timedelta(minutes=10)
STALE_UNTIL = timedelta(minutes=30)
# A reading may be marginally ahead of the server clock; anything beyond this
# is treated as untrustworthy rather than "LIVE".
FUTURE_TOLERANCE = timedelta(minutes=2)


def reading_age(observed_at: datetime, now: datetime) -> timedelta:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return now - observed_at


def classify_freshness(observed_at: datetime | None, now: datetime) -> Freshness:
    """LIVE: age < 10 min. STALE: 10 <= age <= 30 min. OFFLINE: older, missing or future-dated."""
    if observed_at is None:
        return "OFFLINE"
    age = reading_age(observed_at, now)
    if age < -FUTURE_TOLERANCE:
        return "OFFLINE"
    if age < LIVE_BEFORE:
        return "LIVE"
    if age <= STALE_UNTIL:
        return "STALE"
    return "OFFLINE"
