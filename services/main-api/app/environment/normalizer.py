"""Normalize one Aeron reading payload into a K-COSMOS environment reading.

Verified source shape (live, 2026-09-25)::

    {"recordedAt": "2026-09-24T22:34:00.000Z",
     "health": {"network": 4, "battery": 0, ...},
     "location": {...},
     "data": {"<parameter id>": <number>, ...}}

``recordedAt`` is a true UTC instant. Aeron's own dashboard renders it as
"4 hrs ago" relative to its server clock, and its health endpoint reports
``receivedAt`` 14 seconds after it. The ``latest`` route formats it as
``2026-09-24T22:34:00.000Z``; the history route as ``2026-09-24 18:30:00+00``.
No +330 minute correction is applied: doing so would place the measurement
5.5 hours after Aeron received it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.environment.parameters import AERON_PARAMETERS, HEALTH_FIELDS

NORMALIZER_VERSION = 1


class InvalidReadingError(ValueError):
    """The upstream payload cannot be turned into a trustworthy reading."""


@dataclass(frozen=True)
class NormalizedReading:
    station_id: str
    observed_at: datetime
    source_recorded_at_raw: str
    metrics: dict[str, float | None]
    health: dict[str, int | None]
    quality_flags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


def parse_observed_at(value: object) -> datetime:
    """Parse an explicitly zoned Aeron timestamp into an aware UTC datetime.

    Naive timestamps are rejected: the source always sends a UTC designator,
    so a missing one means the contract changed and must not be guessed.
    """
    if not isinstance(value, str) or not value.strip():
        raise InvalidReadingError("recordedAt is missing or not a string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidReadingError("recordedAt is not an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidReadingError("recordedAt has no timezone designator")
    return parsed.astimezone(UTC)


def _metric(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _health(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def normalize_reading(payload: object, station_id: str) -> NormalizedReading:
    if not isinstance(payload, dict) or not payload:
        raise InvalidReadingError("payload is not a non-empty JSON object")
    observed_at = parse_observed_at(payload.get("recordedAt"))
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise InvalidReadingError("payload has no sensor data")

    flags: list[str] = []
    metrics: dict[str, float | None] = {}
    for parameter_id, parameter in AERON_PARAMETERS.items():
        if parameter_id not in data:
            metrics[parameter.field] = None
            flags.append(f"missing:{parameter.field}")
            continue
        number = _metric(data[parameter_id])
        if number is None and data[parameter_id] is not None:
            flags.append(f"non_numeric:{parameter.field}")
        metrics[parameter.field] = number
    flags.extend(f"unknown_parameter:{key}" for key in sorted(data) if key not in AERON_PARAMETERS)
    if all(value is None for value in metrics.values()):
        raise InvalidReadingError("payload contains no recognised numeric metrics")

    raw_health = payload.get("health")
    health_source = raw_health if isinstance(raw_health, dict) else {}
    health = {column: _health(health_source.get(key)) for key, column in HEALTH_FIELDS.items()}

    return NormalizedReading(
        station_id=station_id,
        observed_at=observed_at,
        source_recorded_at_raw=str(payload["recordedAt"]),
        metrics=metrics,
        health=health,
        quality_flags=flags,
        raw_payload={key: payload[key] for key in ("recordedAt", "health", "location", "data") if key in payload},
    )
