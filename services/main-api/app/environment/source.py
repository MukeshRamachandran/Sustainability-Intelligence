"""Aeron upstream access: an authenticated HTTP readings client plus a
Playwright login used only to obtain or refresh the session.

Verified on 2026-09-25: one headless login yields session cookies (the
shortest-lived expires after about one hour); the browser is closed and the
same cookies keep working for plain HTTP requests. Errors carry fixed codes
and messages only - never upstream bodies, URLs with identifiers, or secrets.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from pydantic import SecretStr

Transport = Callable[[str, dict[str, str], float], tuple[int, str, bytes]]


class AeronSourceError(Exception):
    code = "SOURCE_ERROR"
    message = "Aeron source request failed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class SessionExpiredError(AeronSourceError):
    code = "SESSION_EXPIRED"
    message = "Aeron rejected the session (HTTP 401/403)."


class UpstreamTimeoutError(AeronSourceError):
    code = "TIMEOUT"
    message = "Aeron did not respond before the timeout."


class UpstreamNetworkError(AeronSourceError):
    code = "NETWORK_ERROR"
    message = "Aeron could not be reached."


class UpstreamHTTPError(AeronSourceError):
    code = "HTTP_ERROR"

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"Aeron returned HTTP {status}.")


class MalformedResponseError(AeronSourceError):
    code = "MALFORMED_RESPONSE"
    message = "Aeron returned a response that is not a JSON reading object."


class AuthenticationError(AeronSourceError):
    code = "AUTH_FAILED"
    message = "Aeron login did not reach the dashboard."


class AuthenticationNotConfiguredError(AeronSourceError):
    code = "AUTH_NOT_CONFIGURED"
    message = "Aeron login credentials are not configured."


class AuthenticationBackoffError(AeronSourceError):
    code = "AUTH_BACKOFF"
    message = "Aeron login is paused after a recent failure."


def urllib_transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 -- https enforced by settings
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:  # noqa: S310
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", b""
    except TimeoutError:
        raise UpstreamTimeoutError() from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise UpstreamTimeoutError() from None
        raise UpstreamNetworkError() from None
    except OSError:
        raise UpstreamNetworkError() from None


class AeronReadingsClient:
    def __init__(
        self,
        base_url: str,
        station_id: str,
        region: str,
        timeout: float,
        transport: Transport = urllib_transport,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._station_id = station_id
        self._region = region
        self._timeout = timeout
        self._transport = transport

    def latest_url(self) -> str:
        query = urlencode({"mode": "latest", "region": self._region})
        return f"{self._base_url}/stations/{quote(self._station_id, safe='')}/readings?{query}"

    def fetch_latest(self, cookie: str) -> dict[str, Any]:
        headers = {"Cookie": cookie, "Accept": "application/json", "User-Agent": "K-COSMOS-environment-worker/1"}
        status, content_type, body = self._transport(self.latest_url(), headers, self._timeout)
        if status in (401, 403):
            raise SessionExpiredError()
        if status != 200:
            raise UpstreamHTTPError(status)
        if "json" not in content_type.lower():
            raise MalformedResponseError()
        try:
            payload = json.loads(body)
        except ValueError:
            raise MalformedResponseError() from None
        if not isinstance(payload, dict) or not payload:
            raise MalformedResponseError()
        return payload


Login = Callable[[], str]


class PlaywrightLogin:
    """Headless Chromium login. The browser is always closed before returning."""

    USERNAME = 'input[name="username"], input[type="email"], input#username'
    CONTINUE = 'button[type="submit"], button[name="action"][value="default"]'
    PASSWORD = 'input[name="password"], input[type="password"]'  # noqa: S105 -- CSS selector, not a credential
    SUBMIT = 'button[type="submit"], button[name="action"]'

    def __init__(
        self,
        dashboard_url: str,
        cookie_url: str,
        username: SecretStr,
        password: SecretStr,
        timeout_seconds: float,
    ) -> None:
        self._dashboard_url = dashboard_url
        self._cookie_url = cookie_url
        self._username = username
        self._password = password
        self._timeout_ms = timeout_seconds * 1000

    def __call__(self) -> str:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        dashboard_path = urlparse(self._dashboard_url).path or "/dashboard"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(self._dashboard_url, wait_until="domcontentloaded", timeout=self._timeout_ms)
                    page.wait_for_selector(self.USERNAME, timeout=self._timeout_ms)
                    page.fill(self.USERNAME, self._username.get_secret_value())
                    continue_button = page.query_selector(self.CONTINUE)
                    if continue_button:
                        continue_button.click()
                    password = page.wait_for_selector(self.PASSWORD, timeout=self._timeout_ms, state="visible")
                    if password is None:
                        raise AuthenticationError()
                    password.fill(self._password.get_secret_value())
                    submit = page.query_selector(self.SUBMIT)
                    if submit:
                        submit.click()
                    else:
                        password.press("Enter")
                    page.wait_for_url(f"**{dashboard_path}**", timeout=self._timeout_ms)
                    cookies = context.cookies(urls=[self._cookie_url])
                finally:
                    browser.close()
        except PlaywrightError:
            raise AuthenticationError() from None
        header = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies if cookie.get("name"))
        if not header:
            raise AuthenticationError()
        return header


class AeronSession:
    """In-memory session cookie. Logs in only when needed; backs off after a failed login."""

    def __init__(
        self,
        login: Login | None,
        clock: Callable[[], datetime],
        initial_cookie: str | None = None,
        base_backoff: timedelta = timedelta(minutes=5),
        max_backoff: timedelta = timedelta(hours=1),
    ) -> None:
        self._login = login
        self._clock = clock
        self._cookie = initial_cookie or None
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._failures = 0
        self._blocked_until: datetime | None = None

    @property
    def cookie(self) -> str | None:
        return self._cookie

    def invalidate(self) -> None:
        self._cookie = None

    def refresh(self) -> str:
        if self._login is None:
            raise AuthenticationNotConfiguredError()
        now = self._clock()
        if self._blocked_until is not None and now < self._blocked_until:
            raise AuthenticationBackoffError()
        try:
            cookie = self._login()
        except AeronSourceError:
            self._failures += 1
            backoff = min(self._base_backoff * (2 ** (self._failures - 1)), self._max_backoff)
            self._blocked_until = now + backoff
            raise
        self._failures = 0
        self._blocked_until = None
        self._cookie = cookie
        return cookie
