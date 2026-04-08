# ============================================================
#  api/webhook/telegram.py  —  Telegram Webhook Handler
#  Receives POST from Telegram, dispatches commands.
#  Replaces command_listener.py polling thread.
# ============================================================
import json, traceback
from http.server import BaseHTTPRequestHandler

from lib.config import SYMBOLS, TELEGRAM_CHAT_ID
from lib.risk_manager import get_risk_summary
from lib.data_fetcher import get_candles
from lib.chart_generator import generate_chart
import lib.state_store as store
import lib.telegram_notify as tg
from lib.trade_executor import close_all, close_position


def _send(text: str):
    tg.send(text)


def _handle(text: str, username: str):
    parts = text.strip().split()
    cmd   = parts[0].lower().split("@")[0]   # strip @botname suffix if present
    arg   = parts[1].upper() if len(parts) > 1 else ""

    # ── Bot-level commands ──────────────────────────────────
    if cmd == "/start":
        store.enable_trading(by=username)
        _send("✅ <b>Auto Trading ENABLED</b>\nบอทจะส่งสัญญาณและเปิด trade อัตโนมัติสำหรับทุก symbol ที่เปิดอยู่")

    elif cmd == "/stop":
        store.disable_trading(reason="Paused by user", by=username)
        _send("⏸ <b>Auto Trading PAUSED</b>\nบอทยังวิเคราะห์และแจ้งสัญญาณ แต่ไม่เปิด trade\nพิมพ์ /start เพื่อเปิดใหม่")

    elif cmd == "/quit":
        store.stop_bot(by=username)
        _send("🛑 <b>Bot stopped</b>\nหยุดการทำงานแล้ว (cron จะไม่ประมวลผลจนกว่าจะ restart)")

    # ── Symbol-level commands ───────────────────────────────
    elif cmd == "/enable":
        if not arg:
            _send("❓ ระบุ symbol ด้วย เช่น <code>/enable EURUSDm</code>")
            return
        ok = store.enable_symbol(arg, by=username)
        if ok:
            _send(f"✅ <b>{arg}</b> — เปิด auto trade แล้ว")
        else:
            _send(f"❌ ไม่พบ symbol <code>{arg}</code>\nดู /symbols สำหรับรายชื่อ")

    elif cmd == "/disable":
        if not arg:
            _send("❓ ระบุ symbol ด้วย เช่น <code>/disable EURUSDm</code>")
            return
        ok = store.disable_symbol(arg, reason="Disabled by user", by=username)
        if ok:
            _send(f"⏸ <b>{arg}</b> — ปิด auto trade แล้ว (ยังแจ้งสัญญาณ)")
        else:
            _send(f"❌ ไม่พบ symbol <code>{arg}</code>")

    elif cmd == "/symbols":
        lines = ["📋 <b>Symbol Status</b>\n━━━━━━━━━━━━━━━━"]
        trading = store.is_trading_enabled()
        for sym, cfg in SYMBOLS.items():
            enabled = store.is_symbol_enabled(sym)
            has_pos = store.position_exists(sym)
            if trading and enabled:
                icon = "✅ Auto"
            elif enabled:
                icon = "⏸ Alert"
            else:
                icon = "⛔ Off"
            pos_str = "  📌 pos" if has_pos else ""
            lines.append(f"{icon}  <code>{sym}</code>  ({cfg['label']}){pos_str}")
        lines.append("\n/enable SYMBOL — เปิด auto trade")
        lines.append("/disable SYMBOL — เปิดแค่ alert")
        _send("\n".join(lines))

    # ── Info commands ───────────────────────────────────────
    elif cmd == "/status":
        rs     = get_risk_summary()
        status = store.get_status()
        auto   = "✅ ON" if status["trading_enabled"] else "⏸ OFF"
        _send(
            f"📊 <b>Bot Status</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🤖 Auto Trade : {auto}\n"
            f"💰 Balance    : <code>{rs.get('balance', '?')}</code>\n"
            f"📈 Equity     : <code>{rs.get('equity', '?')}</code>\n"
            f"📉 DD         : <code>{rs.get('drawdown_pct', '?')}%</code>\n"
            f"💔 Daily Loss : <code>{rs.get('daily_loss_pct', '?')}%</code>\n"
            f"🔁 Loss Streak: <code>{rs.get('consec_losses', '?')}</code>\n\n"
            f"พิมพ์ /symbols ดูสถานะรายคู่"
        )

    elif cmd == "/close":
        if arg and arg in SYMBOLS:
            close_position(arg, comment="manual_close")
            _send(f"🔒 ส่งคำสั่งปิด position <b>{arg}</b> แล้ว")
        else:
            close_all(comment="manual_close")
            _send("🔒 ส่งคำสั่งปิด position ทั้งหมดแล้ว")

    elif cmd == "/chart":
        sym = arg if arg in SYMBOLS else list(SYMBOLS.keys())[0]
        df  = get_candles(sym, "M5", count=120)
        if df is not None:
            img = generate_chart(df, symbol=sym)
            if img:
                tg.send_chart_bytes(img, caption=f"📊 {sym} M5")
                return
        _send(f"⚠️ ไม่สามารถสร้างกราฟ {sym}")

    # ── Account update command ──────────────────────────────
    elif cmd == "/setbalance":
        # Usage: /setbalance 10000.00 [equity]
        try:
            bal = float(parts[1])
            eq  = float(parts[2]) if len(parts) > 2 else bal
            store.set_account_snapshot({"balance": bal, "equity": eq,
                                        "margin": 0, "currency": "USD"})
            _send(f"💰 Balance อัพเดทเป็น <code>{bal}</code>  Equity: <code>{eq}</code>")
        except (IndexError, ValueError):
            _send("❓ ใช้งาน: <code>/setbalance 10000.00 [equity]</code>")

    else:
        _send(
            "❓ <b>คำสั่งที่ใช้ได้</b>\n\n"
            "<b>Bot level:</b>\n"
            "/start          — เปิด auto trade ทุก symbol\n"
            "/stop           — หยุด auto trade (แจ้งสัญญาณต่อ)\n"
            "/quit           — ปิด bot\n"
            "/status         — ดูสถานะรวม\n"
            "/symbols        — ดูสถานะทุก symbol\n\n"
            "<b>Symbol level:</b>\n"
            "/enable SYMBOL  — เปิด auto trade symbol นั้น\n"
            "/disable SYMBOL — ปิด auto trade symbol นั้น\n"
            "/close [SYMBOL] — ปิด position\n"
            "/chart [SYMBOL] — ดูกราฟ M5\n\n"
            "<b>Account:</b>\n"
            "/setbalance BAL [EQ] — อัพเดทยอด balance ใน bot"
        )


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        # ── Parse body ────────────────────────────────────────
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            update = json.loads(body)
        except json.JSONDecodeError:
            self._reply(400, "Bad JSON")
            return

        # ── Dispatch ──────────────────────────────────────────
        try:
            msg = update.get("message") or update.get("edited_message")
            if msg:
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id == str(TELEGRAM_CHAT_ID):
                    text = msg.get("text", "")
                    user = msg.get("from", {}).get("username", "unknown")
                    if text.startswith("/"):
                        print(f"[Webhook] @{user}: {text}")
                        try:
                            _handle(text, user)
                        except Exception as e:
                            traceback.print_exc()
                            _send(f"❌ <b>Error:</b> <code>{e}</code>")
        except Exception:
            traceback.print_exc()

        # Always return 200 fast — Telegram retries on non-200
        self._reply(200, "ok")

    def _reply(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
