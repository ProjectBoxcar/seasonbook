"""Local Command Center. Keyboard 1–0. Does not touch AlpacaManager."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .explain import explain_pair
from .export import plan_csv_text
from .pipeline import DEFAULT_OUT, Snapshot, snapshot_dict

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
            try:
                self._do_GET()
            except Exception as exc:  # noqa: N802
                msg = f'{{"ok":false,"error":"{exc}"}}'.encode("utf-8")
                try:
                    self._send(500, msg, "application/json")
                except Exception:
                    pass

        def _do_GET(self) -> None:
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
            if path == "/plan.csv":
                self._send(200, plan_csv_text(snap).encode("utf-8"), "text/csv")
                return
            if path in {"/cards.pdf", "/wall.pdf", "/lastblood.pdf", "/board.pdf"}:
                from .book import write_board_pdf, write_cards_pdf, write_last_blood_pdf, write_wall
                from .pipeline import DEFAULT_OUT

                writer = {
                    "/cards.pdf": write_cards_pdf,
                    "/wall.pdf": write_wall,
                    "/lastblood.pdf": write_last_blood_pdf,
                    "/board.pdf": write_board_pdf,
                }[path]
                pdf_path = writer(snap, DEFAULT_OUT)
                self._send(200, pdf_path.read_bytes(), "application/pdf")
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
    print("Keys 1–0  Briefing · Atlas · Heatmap · Plan · Lab · Audit · Why · Horizon · Last Blood · Erosion")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.server_close()
