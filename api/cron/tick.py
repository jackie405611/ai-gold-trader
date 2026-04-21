# ============================================================
#  api/cron/tick.py  —  Main trading loop (Vercel Cron)
#  Called every minute via vercel.json cron schedule.
#
#  Timeframes fetched per tick:
#    H4  (100 bars) — big picture structure  [cached 4h]
#    H1  (100 bars) — zone finding            [cached 1h]
#    M15 (100 bars) — entry confirmation      [cached 15m]
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
        auth = self.headers.get("authorization", "")
        if auth != f"Bearer {os.environ.get('CRON_SECRET', '')}":
            self._reply(401, "Unauthorized")
            return

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

        if not store.is_bot_running():
            print("[Tick] Bot stopped — skipping")
            return

        snap    = store.get_account_snapshot()
        balance = snap.get("balance", 0)
        store.reset_daily_if_needed(today, balance)

        if not market_open():
            print("[Tick] Market closed — skipping")
            return

        if not check_drawdown():
            tg.notify_risk_event("Drawdown / daily loss / consecutive losses limit reached.")
            return

        for symbol, cfg in SYMBOLS.items():
            try:
                self._process_symbol(symbol, cfg)
            except Exception:
                traceback.print_exc()

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

        ask, bid = get_latest_price(symbol)
        if ask == 0:
            print(f"[Tick:{symbol}] ❌ No price")
            return

        if not spread_ok(symbol, cfg, ask, bid):
            return
        if not session_ok(cfg):
            return
        if position_exists(symbol):
            return

        # Fetch multi-timeframe candles (H4 + H1 + M15)
        df_h4  = get_candles(symbol, "H4",  count=100)
        df_h1  = get_candles(symbol, "H1",  count=100)
        df_m15 = get_candles(symbol, "M15", count=100)

        if df_h4 is None or df_h1 is None or df_m15 is None:
            print(f"[Tick:{symbol}] ❌ Missing candle data")
            return

        atr = get_latest_atr(symbol, "M15")

        # Generate 5-layer signal
        signal, info = generate_signal(df_h4, df_h1, df_m15, cfg, ask=ask, bid=bid)
        print(f"[Tick:{symbol}] Signal={signal}  info={info}")

        if signal in ("BUY", "SELL"):
            sl = info.get("sl", 0.0)
            tp = info.get("tp", 0.0)
            if store.should_trade(symbol):
                open_trade(symbol, cfg, signal, atr, ask, bid, sl=sl, tp=tp)
            else:
                tg.notify_trade_signal(symbol, signal, info, ask, bid,
                                       sl=sl, tp=tp, lot=0)

    # ── HTTP helper ───────────────────────────────────────────

    def _reply(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
