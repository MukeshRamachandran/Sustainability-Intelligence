"""Central freshness classification, always computed from server time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

Freshness = Literal["LIVE", "STALE", "OFFLINE"]

# Aeron publishes a new reading about every 7 minutes and delivers it up to ~8
# minutes late; the worker polls every 5. A healthy pipeline can therefore show a
# reading up to ~20 minutes old, so LIVE must cover that or the page flickers STALE.
LIVE_BEFORE = timedelta(minutes=20)
STALE_UNTIL = timedelta(minutes=60)
# A reading may be marginally ahead of the server clock; anything beyond this
# is treated as untrustworthy rather than "LIVE".
FUTURE_TOLERANCE = timedelta(minutes=2)


def reading_age(observed_at: datetime, now: datetime) -> timedelta:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return now - observed_at


def classify_freshness(observed_at: datetime | None, now: datetime) -> Freshness:
    """LIVE: age < 20 min. STALE: 20 <= age <= 60 min. OFFLINE: older, missing or future-dated."""
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
