"""Local Manager/Admin portal server for development.

Serves this directory on http://127.0.0.1:3000, the one origin the backend
allows (see ALLOWED_ORIGINS in services/main-api/compose.yaml) and the one
auth-client.js maps to the API on port 8000.

The only behaviour it adds over `python -m http.server 3000` is `Cache-Control:
no-store` on every response. Plain http.server sends no cache headers, so
browsers apply heuristic caching to the portal's JavaScript and can keep
running an old copy of a module after it has been fixed on disk. During
development the assets must always be the ones on disk.
"""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("KCOSMOS_PORTAL_PORT", "3000"))
ROOT = Path(__file__).resolve().parent


class PortalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


if __name__ == "__main__":
    print(f"K-COSMOS Manager/Admin portal on http://{HOST}:{PORT}  (no-store, serving {ROOT})")
    ThreadingHTTPServer((HOST, PORT), PortalHandler).serve_forever()
