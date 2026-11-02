"""Normalize one Aeron v1 ``/timeseries`` response into a K-COSMOS reading.

Verified source shape (live, 2026-11-02)::

    {"station": "<station uuid>",
     "resolution": "latest",
     "reading": {"timestamp": "2026-11-02T10:58:01.000Z",
                 "epoch_ms": 1793617081000,
                 "values": {"<parameter id>": <number>, ...}}}

``timestamp`` is a true UTC instant (see AERON_REAL_API_CONTRACT.md). No
+330 minute correction is applied and naive timestamps are rejected.
Missing or non-numeric values become ``None`` with a quality flag, never 0.
Unknown parameter IDs are kept in ``unmapped_values``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.environment.parameters import AERON_PARAMETERS

NORMALIZER_VERSION = 2
# ``timestamp`` and ``epoch_ms`` describe the same instant; allow rounding only.
EPOCH_TOLERANCE_MS = 1000


class InvalidReadingError(ValueError):
    """The upstream payload cannot be turned into a trustworthy reading."""


class StationMismatchError(InvalidReadingError):
    """The response names a different station from the one requested."""


@dataclass(frozen=True)
class NormalizedReading:
    station_id: str
    observed_at: datetime
    source_recorded_at_raw: str
    source_epoch_ms: int | None
    metrics: dict[str, float | None]
    unmapped_values: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


def parse_observed_at(value: object) -> datetime:
    """Parse an explicitly zoned Aeron timestamp into an aware UTC datetime.

    Naive timestamps are rejected: the source always sends a UTC designator,
    so a missing one means the contract changed and must not be guessed.
    """
    if not isinstance(value, str) or not value.strip():
        raise InvalidReadingError("timestamp is missing or not a string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidReadingError("timestamp is not an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidReadingError("timestamp has no timezone designator")
    return parsed.astimezone(UTC)


def _metric(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _epoch_ms(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return int(value)


def normalize_timeseries(payload: object, station_id: str) -> NormalizedReading:
    if not isinstance(payload, dict) or not payload:
        raise InvalidReadingError("payload is not a non-empty JSON object")
    source_station = payload.get("station")
    if source_station is not None and source_station != station_id:
        raise StationMismatchError("response is for a different station")
    reading = payload.get("reading")
    if not isinstance(reading, dict) or not reading:
        raise InvalidReadingError("payload has no reading object")
    observed_at = parse_observed_at(reading.get("timestamp"))
    values = reading.get("values")
    if not isinstance(values, dict) or not values:
        raise InvalidReadingError("reading has no sensor values")

    flags: list[str] = []
    epoch_ms = _epoch_ms(reading.get("epoch_ms"))
    if reading.get("epoch_ms") is not None and epoch_ms is None:
        flags.append("invalid_epoch_ms")
    if epoch_ms is not None and abs(epoch_ms - observed_at.timestamp() * 1000) > EPOCH_TOLERANCE_MS:
        flags.append("epoch_ms_mismatch")

    metrics: dict[str, float | None] = {}
    for parameter_id, parameter in AERON_PARAMETERS.items():
        if parameter_id not in values:
            metrics[parameter.field] = None
            flags.append(f"missing:{parameter.field}")
            continue
        number = _metric(values[parameter_id])
        if number is None and values[parameter_id] is not None:
            flags.append(f"non_numeric:{parameter.field}")
        metrics[parameter.field] = number
    unmapped = {key: values[key] for key in sorted(values) if key not in AERON_PARAMETERS}
    flags.extend(f"unknown_parameter:{key}" for key in unmapped)
    if all(value is None for value in metrics.values()):
        raise InvalidReadingError("payload contains no recognised numeric metrics")

    return NormalizedReading(
        station_id=station_id,
        observed_at=observed_at,
        source_recorded_at_raw=str(reading["timestamp"]),
        source_epoch_ms=epoch_ms,
        metrics=metrics,
        unmapped_values=unmapped,
        quality_flags=flags,
        raw_payload={key: payload[key] for key in ("station", "resolution", "reading") if key in payload},
    )
