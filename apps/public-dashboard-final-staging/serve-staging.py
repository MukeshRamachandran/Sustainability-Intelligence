"""Local staging server with a narrow same-origin public API proxy.

Production remains Browser -> Nginx -> /api/public/* -> Main API.
This helper exists only to test that same path on http://127.0.0.1:3001.

Only the read-only public dashboard routes are proxied.  Every other path is
served as a static staging asset, so no authenticated or admin route can be
reached through this helper.
"""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = int(os.environ.get("KCOSMOS_STAGING_PORT", "3001"))
UPSTREAM_BASE = os.environ.get("KCOSMOS_API_BASE", "http://127.0.0.1:8000").rstrip("/")

# The exact public contract the final dashboard consumes.  Adding a route here
# is the only supported way to widen the proxy.
PUBLIC_ROUTES = frozenset(
    {
        "/api/public/dashboard",
        "/api/public/dashboard/history",
    }
)
ROOT = Path(__file__).resolve().parent


class StagingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _proxy(self, route: str, query: str) -> None:
        upstream = urlsplit(UPSTREAM_BASE)
        target = urlunsplit((upstream.scheme, upstream.netloc, route, query, ""))
        try:
            with urlopen(Request(target, headers={"Accept": "application/json"}), timeout=10) as response:
                body = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as error:
            self.send_error(error.code, error.reason)
        except URLError:
            self.send_error(502, "Main API unavailable")

    def do_GET(self) -> None:  # noqa: N802
        route, _, query = self.path.partition("?")
        if route in PUBLIC_ROUTES:
            self._proxy(route, query)
            return
        super().do_GET()


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), StagingHandler).serve_forever()
