#!/usr/bin/env python3
"""Local development only: serve the public dashboard and forward its API calls.

The dashboard calls ``/api/...`` on its own origin; in production Nginx routes
that to the API. Locally this server does the same for GET/HEAD requests:

    python deployment/scripts/dev-server.py --port 3000
    # then open http://127.0.0.1:3000

It binds to loopback only, forwards nothing but ``/api/`` and ``/health/`` to
the API (default http://127.0.0.1:8000), and never contacts Aeron. Not for
production use; production uses static-server.py behind Nginx.
"""

from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROXIED_PREFIXES = ("/api/", "/health/")
FORWARDED_RESPONSE_HEADERS = {"content-type", "cache-control"}
REPO_ROOT = Path(__file__).resolve().parents[2]


class DevHandler(SimpleHTTPRequestHandler):
    api_base = "http://127.0.0.1:8000"

    def list_directory(self, path: str):  # type: ignore[override]
        self.send_error(404, "Not found")
        return None

    def do_GET(self) -> None:  # noqa: N802 -- http.server naming
        if self.path.startswith(PROXIED_PREFIXES):
            self._proxy()
        else:
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self.path.startswith(PROXIED_PREFIXES):
            self._proxy()
        else:
            super().do_HEAD()

    def _proxy(self) -> None:
        request = urllib.request.Request(  # noqa: S310 -- fixed loopback http base
            self.api_base + self.path, method=self.command, headers={"Accept": self.headers.get("Accept", "*/*")}
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as upstream:  # noqa: S310
                status, headers, body = upstream.status, upstream.headers, upstream.read()
        except urllib.error.HTTPError as exc:
            status, headers, body = exc.code, exc.headers, exc.read()
        except (urllib.error.URLError, OSError):
            self.send_error(502, "API is not reachable on " + self.api_base)
            return
        self.send_response(status)
        for name, value in headers.items():
            if name.lower() in FORWARDED_RESPONSE_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def end_headers(self) -> None:
        if not self.path.startswith(PROXIED_PREFIXES):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the public dashboard locally with the API forwarded.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--directory", type=Path, default=REPO_ROOT / "apps" / "public-dashboard")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL (loopback only)")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("dev server must bind to loopback")
    api = urlparse(args.api)
    if api.scheme != "http" or api.hostname not in {"127.0.0.1", "localhost", "::1"} or api.path not in {"", "/"}:
        raise SystemExit("--api must be a loopback http://host:port base")
    directory = args.directory.resolve()
    if not directory.is_dir():
        raise SystemExit(f"directory does not exist: {directory}")

    handler = partial(type("Handler", (DevHandler,), {"api_base": args.api.rstrip("/")}), directory=str(directory))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"serving {directory} on http://{args.host}:{args.port} (API: {args.api})")
    server.serve_forever()


if __name__ == "__main__":
    main()
