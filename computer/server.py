#!/usr/bin/env python3
"""Owner-only virtual-computer HTTP API for the free Render web service.

Public GET /health is for Render's health check (no secrets). Every real
operation requires Authorization: Bearer $BOX_TOKEN.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NEXORA_VBOX_LOCAL", "1")

from sglbot import vbox  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s vbox: %(message)s")
log = logging.getLogger("vbox")
HOST = os.getenv("VBOX_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT") or os.getenv("VBOX_PORT") or 10000)


def _auth_ok(handler: BaseHTTPRequestHandler) -> bool:
    token = (os.getenv("BOX_TOKEN") or "").strip()
    if not token:
        return False
    got = (handler.headers.get("Authorization") or "").strip()
    if got.lower().startswith("bearer "):
        got = got[7:].strip()
    if not got:
        return False
    return hmac.compare_digest(got, token)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s " + fmt, self.address_string(), *args)

    def _send(self, code: int, body, headers: dict | None = None) -> None:
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            # Public on purpose: Render's free-plan health check has no auth header.
            self._send(200, {"ok": True, "service": "nexora-computer"})
            return
        if path in ("/v1/health",):
            if not _auth_ok(self):
                self._send(401, {"error": "unauthorized"})
                return
            self._send(200, {"ok": True, "service": "nexora-vbox", "local": True, "chrome": Path(vbox.CHROME).exists()})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/v1/run":
            self._send(404, {"error": "not found"})
            return
        if not _auth_ok(self):
            self._send(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_500_000:
            self._send(413, {"error": "payload too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            self._send(400, {"error": "invalid json"})
            return
        op = (payload.get("op") or "").strip()
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        try:
            result = vbox._dispatch(op, args)
        except Exception as exc:
            log.exception("op %s failed", op)
            self._send(500, {"error": type(exc).__name__ + ": " + str(exc)[:200]})
            return
        files = result.pop("_files", None) or []
        out_files = []
        for f in files:
            out_files.append({
                "name": f.get("name") or "file",
                "mime": f.get("mime") or "application/octet-stream",
                "size": f.get("size") or len(f.get("data") or b""),
                "data": base64.b64encode(f.get("data") or b"").decode(),
            })
        result["files"] = out_files
        self._send(200, result)


def main() -> int:
    if not (os.getenv("BOX_TOKEN") or "").strip():
        log.error("BOX_TOKEN is missing")
        return 1
    vbox._ensure()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    log.info("listening on %s:%s chrome=%s", HOST, PORT, Path(vbox.CHROME).exists())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
