"""Local Command Center. Keyboard 1–8. Does not touch AlpacaManager."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .explain import explain_pair
from .pipeline import Snapshot, snapshot_dict

DESK = Path(__file__).resolve().parent / "static" / "desk.html"


def serve(snap: Snapshot, host: str = "127.0.0.1", port: int = 8765) -> None:
    payload = json.dumps(snapshot_dict(snap)).encode("utf-8")
    html = DESK.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter desk
            if args and str(args[0]).startswith("GET /api"):
                return
            super().log_message(fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send(200, html, "text/html; charset=utf-8")
                return
            if path == "/api/snapshot":
                self._send(200, payload, "application/json")
                return
            if path == "/health":
                self._send(200, b'{"ok":true}', "application/json")
                return
            self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, b'{"ok":false,"error":"bad json"}', "application/json")
                return
            if path == "/api/explain":
                result = explain_pair(
                    snap.herd,
                    snap.engine,
                    str(body.get("dam") or ""),
                    str(body.get("sire") or ""),
                )
                self._send(200, json.dumps(result).encode("utf-8"), "application/json")
                return
            self._send(404, b"not found", "text/plain")

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Season Book desk  http://{host}:{port}/")
    print("Keys 1–8  Briefing · Atlas · Heatmap · Plan · Mate lab · Audit · Why · Three seasons")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.server_close()
