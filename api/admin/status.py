# ============================================================
#  api/admin/status.py  —  HTTP status endpoint
#  GET /api/admin/status → JSON bot state (for monitoring)
# ============================================================
import os, json
from http.server import BaseHTTPRequestHandler

from lib.risk_manager import get_risk_summary
import lib.state_store as store
from lib.config import SYMBOLS


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Simple bearer token auth (use CRON_SECRET for convenience)
        auth = self.headers.get("authorization", "")
        if auth != f"Bearer {os.environ.get('CRON_SECRET', '')}":
            self._reply(401, {"error": "Unauthorized"})
            return

        status  = store.get_status()
        risk    = get_risk_summary()
        symbols = {
            sym: {
                "enabled":       store.is_symbol_enabled(sym),
                "position_open": store.position_exists(sym),
                "position":      store.get_open_position(sym),
            }
            for sym in SYMBOLS
        }

        self._reply(200, {
            "bot":     status,
            "risk":    risk,
            "symbols": symbols,
        })

    def _reply(self, code: int, data: dict):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
