"""Local staging server with a narrow same-origin public API proxy.

Production remains Browser -> Nginx -> /api/public/dashboard -> Main API.
This helper exists only to test that same path on http://127.0.0.1:3001.
"""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = int(os.environ.get("KCOSMOS_STAGING_PORT", "3001"))
PUBLIC_ROUTE = "/api/public/dashboard"
UPSTREAM = "http://127.0.0.1:8000/api/public/dashboard"
ROOT = Path(__file__).resolve().parent


class StagingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != PUBLIC_ROUTE:
            super().do_GET()
            return
        try:
            with urlopen(Request(UPSTREAM, headers={"Accept": "application/json"}), timeout=10) as response:
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


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), StagingHandler).serve_forever()
