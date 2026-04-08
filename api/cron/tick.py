# ============================================================
#  api/cron/tick.py  —  Main trading loop (Vercel Cron)
#  Called every minute via vercel.json cron schedule.
#  Replaces main.py while-loop.
# ============================================================
import os, traceback
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone

from lib.config import SYMBOLS
from lib.data_fetcher import get_candles, get_latest_price, get_latest_atr
from lib.ai_strategy import generate_signal
from lib.filters import spread_ok, session_ok, position_exists, market_open
from lib.risk_manager import check_drawdown, get_risk_summary
from lib.trade_executor import open_trade, close_all
import lib.state_store as store
import lib.telegram_notify as tg


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # ── 1. Verify Vercel cron secret ──────────────────────
        auth = self.headers.get("authorization", "")
        if auth != f"Bearer {os.environ.get('CRON_SECRET', '')}":
            self._reply(401, "Unauthorized")
            return

        # ── 2. Cron concurrency lock ──────────────────────────
        if not store.acquire_cron_lock():
            self._reply(200, "locked")
            return

        try:
            self._run_tick()
        except Exception:
            traceback.print_exc()
        finally:
            store.release_cron_lock()

        self._reply(200, "ok")

    # ── Main tick logic ───────────────────────────────────────

    def _run_tick(self):
        now_utc = datetime.now(timezone.utc)
        today   = now_utc.strftime("%Y-%m-%d")

        # Bot stopped?
        if not store.is_bot_running():
            print("[Tick] Bot stopped — skipping")
            return

        # Daily reset
        snap    = store.get_account_snapshot()
        balance = snap.get("balance", 0)
        store.reset_daily_if_needed(today, balance)

        # Market closed?
        if not market_open():
            print("[Tick] Market closed — skipping")
            return

        # Global risk gate
        if not check_drawdown():
            tg.notify_risk_event("Drawdown / daily loss / consecutive losses limit reached.")
            return

        # ── Per-symbol loop ───────────────────────────────────
        for symbol, cfg in SYMBOLS.items():
            try:
                self._process_symbol(symbol, cfg)
            except Exception:
                traceback.print_exc()

        # ── Periodic summary every 30 invocations ────────────
        count = store.increment_invocation()
        if count % 30 == 0:
            rs = get_risk_summary()
            tg.send(
                f"📊 <b>Periodic Summary</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💰 Balance : <code>{rs.get('balance', '?')}</code>\n"
                f"📈 Equity  : <code>{rs.get('equity', '?')}</code>\n"
                f"📉 DD      : <code>{rs.get('drawdown_pct', '?')}%</code>\n"
                f"💔 DailyL  : <code>{rs.get('daily_loss_pct', '?')}%</code>\n"
                f"🔁 Streak  : <code>{rs.get('consec_losses', '?')}</code>"
            )

    def _process_symbol(self, symbol: str, cfg: dict):
        print(f"\n[Tick] ── {symbol} ──")

        # Fetch price
        ask, bid = get_latest_price(symbol)
        if ask == 0:
            print(f"[Tick:{symbol}] ❌ No price")
            return

        # Filters
        if not spread_ok(symbol, cfg, ask, bid):
            return
        if not session_ok(cfg):
            return
        if position_exists(symbol):
            return

        # Fetch candles
        df_m5 = get_candles(symbol, "M5", count=200)
        df_m1 = get_candles(symbol, "M1", count=100)
        if df_m5 is None or df_m1 is None:
            print(f"[Tick:{symbol}] ❌ No candles")
            return

        atr = get_latest_atr(symbol, "M1")

        # Generate signal
        signal, info = generate_signal(df_m5, df_m1, cfg)
        print(f"[Tick:{symbol}] Signal={signal}  info={info}")

        if signal in ("BUY", "SELL"):
            if store.should_trade(symbol):
                open_trade(symbol, cfg, signal, atr, ask, bid)
            else:
                # Alert-only mode
                tg.notify_trade_signal(symbol, signal, info, ask, bid,
                                       sl=0, tp=0, lot=0)

    # ── HTTP helper ───────────────────────────────────────────

    def _reply(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass  # suppress default HTTP server logs
