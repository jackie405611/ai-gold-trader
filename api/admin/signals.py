# ============================================================
#  api/admin/signals.py  —  Signal history + stats endpoint
#  GET /api/admin/signals → JSON signal log + aggregated stats
# ============================================================
import os, json
from http.server import BaseHTTPRequestHandler
from collections import defaultdict

import lib.state_store as store


def _compute_stats(signals: list) -> dict:
    total      = len(signals)
    buy_count  = sum(1 for s in signals if s.get("signal") == "BUY")
    sell_count = sum(1 for s in signals if s.get("signal") == "SELL")
    no_trade   = total - buy_count - sell_count

    trades = [s for s in signals if s.get("signal") in ("BUY", "SELL")]
    sim_trades  = len(trades)
    sim_wins    = sum(1 for s in trades if s.get("sim_outcome") == "TP")
    sim_losses  = sum(1 for s in trades if s.get("sim_outcome") == "SL")
    sim_open    = sum(1 for s in trades if s.get("sim_outcome") is None)

    closed = sim_wins + sim_losses
    win_rate = round(sim_wins / closed * 100, 1) if closed else 0.0

    rr_vals = [s["sim_pnl_r"] for s in trades if s.get("sim_pnl_r") is not None]
    avg_rr  = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else 0.0

    # Breakdown by entry_type
    by_entry: dict = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0, "open": 0})
    for s in trades:
        et = s.get("entry_type") or "UNKNOWN"
        by_entry[et]["total"]  += 1
        outcome = s.get("sim_outcome")
        if outcome == "TP":
            by_entry[et]["wins"]   += 1
        elif outcome == "SL":
            by_entry[et]["losses"] += 1
        else:
            by_entry[et]["open"]   += 1

    # Breakdown by H4 structure
    by_h4: dict = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0})
    for s in trades:
        h4 = s.get("h4_structure") or "UNKNOWN"
        by_h4[h4]["total"] += 1
        if s.get("sim_outcome") == "TP":
            by_h4[h4]["wins"]   += 1
        elif s.get("sim_outcome") == "SL":
            by_h4[h4]["losses"] += 1

    return {
        "total":          total,
        "buy_count":      buy_count,
        "sell_count":     sell_count,
        "no_trade_count": no_trade,
        "sim_trades":     sim_trades,
        "sim_wins":       sim_wins,
        "sim_losses":     sim_losses,
        "sim_open":       sim_open,
        "win_rate_pct":   win_rate,
        "avg_rr":         avg_rr,
        "by_entry_type":  dict(by_entry),
        "by_h4_structure":dict(by_h4),
    }


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        auth = self.headers.get("authorization", "")
        expected = os.environ.get("CRON_SECRET", "")
        if auth != f"Bearer {expected}":
            self._reply(401, {"error": "Unauthorized"})
            return

        try:
            signals = store.get_signal_history(n=100)
            stats   = _compute_stats(store.get_signal_history(n=500))
            self._reply(200, {"signals": signals, "stats": stats})
        except Exception as exc:
            self._reply(500, {"error": str(exc)})

    def _reply(self, code: int, body: dict):
        raw = json.dumps(body, ensure_ascii=False, default=str)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw.encode())

    def log_message(self, *args):
        pass
