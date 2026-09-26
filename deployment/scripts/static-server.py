#!/usr/bin/env python3
"""Bind a static frontend to 127.0.0.1 for Nginx to proxy.

The public dashboard and manager portal are plain files with no build step.
Nginx on port 443 is the only public entry point. This server refuses
directory listings and is started by systemd, not from an interactive shell.
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ASSET_SUFFIXES = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
}


class StaticHandler(SimpleHTTPRequestHandler):
    def list_directory(self, path: str):  # type: ignore[override]
        self.send_error(404, "Not found")
        return None

    def end_headers(self) -> None:
        request_path = self.path.split("?", 1)[0]
        suffix = Path(request_path).suffix.lower()
        if suffix in ASSET_SUFFIXES:
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a static directory on localhost.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("static server must bind to loopback")

    directory = args.directory.resolve()
    if not directory.is_dir():
        raise SystemExit(f"directory does not exist: {directory}")

    handler = partial(StaticHandler, directory=str(directory))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"serving {directory} on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
