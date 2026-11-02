"""Aeron REST API v1 client against mocked HTTP. No request reaches Aeron."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.environment.source import (
    AeronApiClient,
    AeronSourceError,
    AuthenticationError,
    MalformedResponseError,
    PermissionDeniedError,
    RateLimitedError,
    ResourceNotFoundError,
    UpstreamHTTPError,
    UpstreamNetworkError,
    UpstreamTimeoutError,
)
from tests.environment_support import real_station_id, v1_fixture

STATION = real_station_id()
BASE = "https://live3.aeronsystems.com/api/v1"
API_KEY = "test-key-do-not-leak-0123456789"
NOW = datetime(2026, 11, 2, 11, 0, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[no-any-return]


def json_response(body: object, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def make_client(recorder: Recorder, sleeps: list[float] | None = None, max_attempts: int = 3) -> AeronApiClient:
    return AeronApiClient(
        BASE,
        SecretStr(API_KEY),
        STATION,
        max_attempts=max_attempts,
        transport=httpx.MockTransport(recorder),
        sleep=(sleeps.append if sleeps is not None else lambda _seconds: None),
        jitter=lambda: 1.0,
        clock=lambda: NOW,
    )


def test_stations_request_uses_bearer_auth_and_no_query() -> None:
    recorder = Recorder([json_response(v1_fixture()["stations"])])

    body = make_client(recorder).stations()

    [request] = recorder.requests
    assert str(request.url) == f"{BASE}/stations"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert request.headers["Accept"] == "application/json"
    assert body["stations"][0]["id"] == STATION


def test_parameters_request_sends_only_the_station_parameter() -> None:
    recorder = Recorder([json_response(v1_fixture()["parameters"])])

    body = make_client(recorder).parameters()

    assert str(recorder.requests[0].url) == f"{BASE}/parameters?station={STATION}"
    assert len(body["parameters"]) == 35


def test_latest_timeseries_request_and_rate_limit_headers() -> None:
    headers = {"X-Ratelimit-Remaining-Minute": "57", "X-Ratelimit-Remaining-Day": "9991"}
    recorder = Recorder([json_response(v1_fixture()["timeseries_latest"], headers=headers)])
    client = make_client(recorder)

    body = client.latest_timeseries()

    assert str(recorder.requests[0].url) == f"{BASE}/timeseries?station={STATION}"
    assert body["reading"]["timestamp"] == "2026-11-02T10:58:01.000Z"
    assert client.rate_limit is not None
    assert (client.rate_limit.remaining_minute, client.rate_limit.remaining_day) == (57, 9991)


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AuthenticationError), (403, PermissionDeniedError), (404, ResourceNotFoundError)],
)
def test_auth_permission_and_not_found_are_never_retried(status: int, error: type[AeronSourceError]) -> None:
    recorder = Recorder([json_response({"error": "x"}, status)])
    sleeps: list[float] = []

    with pytest.raises(error):
        make_client(recorder, sleeps).latest_timeseries()

    assert len(recorder.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "120"}, 120.0),
        ({"Retry-After": "Mon, 02 Nov 2026 11:05:00 GMT"}, 300.0),
        ({"X-Ratelimit-Reset": str(int(NOW.timestamp()) + 42)}, 42.0),
        ({"Retry-After": "999999"}, 3600.0),
        ({}, None),
    ],
)
def test_rate_limit_is_not_retried_and_reports_retry_after(headers: dict[str, str], expected: float | None) -> None:
    recorder = Recorder([json_response({"error": "slow down"}, 429, headers)])

    with pytest.raises(RateLimitedError) as caught:
        make_client(recorder).latest_timeseries()

    assert caught.value.retry_after_seconds == expected
    assert len(recorder.requests) == 1


def test_server_errors_and_timeouts_retry_with_bounded_jittered_backoff() -> None:
    recorder = Recorder(
        [
            json_response({}, 503),
            httpx.ReadTimeout("slow"),
            json_response(v1_fixture()["timeseries_latest"]),
        ]
    )
    sleeps: list[float] = []

    body = make_client(recorder, sleeps).latest_timeseries()

    assert body["station"] == STATION
    assert len(recorder.requests) == 3
    assert sleeps == [1.0, 2.0]  # jitter fixed at its ceiling: base * 2**n, capped


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.ConnectTimeout("x"), UpstreamTimeoutError),
        (httpx.ReadTimeout("x"), UpstreamTimeoutError),
        (httpx.ConnectError("x"), UpstreamNetworkError),
    ],
)
def test_persistent_transport_failures_give_up_after_max_attempts(
    failure: Exception, error: type[AeronSourceError]
) -> None:
    recorder = Recorder([failure, failure, failure])

    with pytest.raises(error):
        make_client(recorder).latest_timeseries()

    assert len(recorder.requests) == 3


def test_persistent_server_error_gives_up_with_its_status() -> None:
    recorder = Recorder([json_response({}, 502)] * 3)
    with pytest.raises(UpstreamHTTPError) as caught:
        make_client(recorder).latest_timeseries()
    assert caught.value.status == 502


def test_redirects_are_not_followed_so_the_key_stays_on_aeron() -> None:
    recorder = Recorder([httpx.Response(302, headers={"Location": "https://elsewhere.example/steal"})])
    with pytest.raises(UpstreamHTTPError):
        make_client(recorder).latest_timeseries()
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>login</html>", headers={"Content-Type": "text/html"}),
        httpx.Response(200, content=b"not json", headers={"Content-Type": "application/json"}),
        json_response({}),
        json_response([]),
        json_response(None),
    ],
)
def test_malformed_json_is_rejected(response: httpx.Response) -> None:
    with pytest.raises(MalformedResponseError):
        make_client(Recorder([response])).latest_timeseries()


def test_errors_never_contain_the_api_key() -> None:
    recorder = Recorder([json_response({"error": API_KEY}, 401)])
    with pytest.raises(AeronSourceError) as caught:
        make_client(recorder).latest_timeseries()
    assert API_KEY not in str(caught.value)
    assert API_KEY not in repr(caught.value)
