"""Aeron Live3 REST API v1 client (Bearer API key).

Verified live on 2026-11-02 against ``https://live3.aeronsystems.com/api/v1``:
``GET /stations``, ``GET /parameters?station=`` and ``GET /timeseries?station=``
all answer 200 JSON. Responses carry ``X-Ratelimit-Limit-Minute: 60`` and
``X-Ratelimit-Limit-Day: 10000``.

Only transient failures (timeout, network, 5xx) are retried, with bounded
exponential backoff and full jitter. 401/403/404/429 are never retried here;
the worker decides when to try again. Errors carry fixed codes and messages
only - never upstream bodies, request headers or the API key.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import SecretStr

USER_AGENT = "K-COSMOS-environment-worker/2"
# Never wait longer than this on a server-supplied Retry-After.
MAX_RETRY_AFTER_SECONDS = 3600.0


class AeronSourceError(Exception):
    code = "SOURCE_ERROR"
    message = "Aeron source request failed."
    retryable = False

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class AuthenticationError(AeronSourceError):
    code = "AUTH_FAILED"
    message = "Aeron rejected the API key (HTTP 401)."


class PermissionDeniedError(AeronSourceError):
    code = "FORBIDDEN"
    message = "The API key is not allowed to read this resource (HTTP 403)."


class ResourceNotFoundError(AeronSourceError):
    code = "NOT_FOUND"
    message = "Aeron does not know this endpoint or station (HTTP 404)."


class RateLimitedError(AeronSourceError):
    code = "RATE_LIMITED"
    message = "Aeron rate limit exceeded (HTTP 429)."

    def __init__(self, retry_after_seconds: float | None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__()


class UpstreamTimeoutError(AeronSourceError):
    code = "TIMEOUT"
    message = "Aeron did not respond before the timeout."
    retryable = True


class UpstreamNetworkError(AeronSourceError):
    code = "NETWORK_ERROR"
    message = "Aeron could not be reached."
    retryable = True


class UpstreamHTTPError(AeronSourceError):
    code = "HTTP_ERROR"

    def __init__(self, status: int) -> None:
        self.status = status
        self.retryable = status >= 500
        super().__init__(f"Aeron returned HTTP {status}.")


class MalformedResponseError(AeronSourceError):
    code = "MALFORMED_RESPONSE"
    message = "Aeron returned a response that is not a JSON object."


@dataclass(frozen=True)
class RateLimitState:
    remaining_minute: int | None
    remaining_day: int | None


def _int_header(headers: httpx.Headers, name: str) -> int | None:
    value = headers.get(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def parse_retry_after(headers: httpx.Headers, now: datetime) -> float | None:
    """Seconds to wait from ``Retry-After`` (seconds or HTTP date), else ``X-Ratelimit-Reset`` (epoch seconds)."""
    value = headers.get("Retry-After")
    if value is not None:
        value = value.strip()
        if value.isdigit():
            return min(float(value), MAX_RETRY_AFTER_SECONDS)
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            when = None
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return min(max(0.0, (when - now).total_seconds()), MAX_RETRY_AFTER_SECONDS)
    reset = _int_header(headers, "X-Ratelimit-Reset")
    if reset is not None:
        return min(max(0.0, reset - now.timestamp()), MAX_RETRY_AFTER_SECONDS)
    return None


class AeronApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: SecretStr,
        station_id: str,
        *,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 8.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,  # noqa: S311 -- backoff jitter, not cryptography
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._station_id = station_id
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._sleep = sleep
        self._jitter = jitter
        self._clock = clock
        self.rate_limit: RateLimitState | None = None
        # One pooled client per worker: connections are reused across cycles.
        # Redirects are refused so the Authorization header never leaves this origin.
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def stations(self) -> dict[str, Any]:
        return self._get("/stations", {})

    def parameters(self) -> dict[str, Any]:
        return self._get("/parameters", {"station": self._station_id})

    def latest_timeseries(self) -> dict[str, Any]:
        return self._get("/timeseries", {"station": self._station_id})

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        attempt = 0
        while True:
            attempt += 1
            try:
                return self._get_once(path, params)
            except AeronSourceError as exc:
                if not exc.retryable or attempt >= self._max_attempts:
                    raise
            ceiling = min(self._backoff_max, self._backoff_base * 2.0 ** (attempt - 1))
            self._sleep(self._jitter() * ceiling)

    def _get_once(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException:
            raise UpstreamTimeoutError() from None
        except httpx.HTTPError:
            raise UpstreamNetworkError() from None

        self.rate_limit = RateLimitState(
            remaining_minute=_int_header(response.headers, "X-Ratelimit-Remaining-Minute"),
            remaining_day=_int_header(response.headers, "X-Ratelimit-Remaining-Day"),
        )
        status = response.status_code
        if status == 401:
            raise AuthenticationError()
        if status == 403:
            raise PermissionDeniedError()
        if status == 404:
            raise ResourceNotFoundError()
        if status == 429:
            raise RateLimitedError(parse_retry_after(response.headers, self._clock()))
        if status != 200:
            raise UpstreamHTTPError(status)
        if "json" not in response.headers.get("Content-Type", "").lower():
            raise MalformedResponseError()
        try:
            payload = response.json()
        except ValueError:
            raise MalformedResponseError() from None
        if not isinstance(payload, dict) or not payload:
            raise MalformedResponseError()
        return payload
