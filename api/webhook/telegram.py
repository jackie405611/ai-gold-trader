# ============================================================
#  api/webhook/telegram.py  —  Telegram Webhook Handler
#  Receives POST from Telegram, dispatches all bot commands.
#
#  Commands:
#    /start              — เปิด auto trade ทุก symbol
#    /stop               — หยุด auto trade (แจ้งสัญญาณต่อ)
#    /quit               — ปิด bot
#    /status             — สถานะรวม (balance, DD, streak)
#    /symbols            — สถานะทุก symbol
#    /enable SYMBOL      — เปิด auto trade symbol นั้น
#    /disable SYMBOL     — ปิด auto trade symbol นั้น
#    /signal [SYMBOL]    — วิเคราะห์สัญญาณ on-demand
#    /positions          — ดู open positions ทั้งหมด
#    /close [SYMBOL]     — ปิด position
#    /chart [SYMBOL] [TF]— ดูกราฟ (TF: M15/H1/H4, default M15)
#    /setmode SYMBOL MODE— บังคับ entry type (pullback/breakout/range/auto)
#    /mode SYMBOL        — ดู mode ปัจจุบัน
#    /setbalance BAL [EQ]— อัพเดท balance ใน bot
#    /help               — แสดงคำสั่งทั้งหมด
# ============================================================
import json, traceback
from http.server import BaseHTTPRequestHandler

from lib.config import SYMBOLS, TELEGRAM_CHAT_ID
from lib.risk_manager import get_risk_summary
from lib.data_fetcher import get_candles, get_latest_price
from lib.ai_strategy import generate_signal
from lib.chart_generator import generate_chart
import lib.state_store as store
import lib.telegram_notify as tg
from lib.trade_executor import close_all, close_position

_VALID_TF    = {"M15", "H1", "H4", "M5"}
_VALID_MODES = {"auto", "pullback", "pullback_sell", "breakout", "range"}


def _resolve_symbol(raw: str) -> str | None:
    """
    Match user input to a SYMBOLS key.
    Tries in order: exact → case-insensitive → label (e.g. "GOLD").
    Returns the correct key or None if not found.
    """
    if not raw:
        return None
    if raw in SYMBOLS:
        return raw
    raw_up = raw.upper()
    for key in SYMBOLS:
        if key.upper() == raw_up:
            return key
    for key, cfg in SYMBOLS.items():
        if cfg.get("label", "").upper() == raw_up:
            return key
    return None


def _send(text: str):
    tg.send(text)


# ── Command handlers ──────────────────────────────────────────

def _cmd_start(username: str):
    store.enable_trading(by=username)
    _send(
        "✅ <b>Auto Trading ENABLED</b>\n"
        "บอทจะเปิด trade อัตโนมัติสำหรับทุก symbol ที่เปิดอยู่\n"
        "พิมพ์ /symbols ดูสถานะแต่ละคู่"
    )


def _cmd_stop(username: str):
    store.disable_trading(reason="Paused by user", by=username)
    _send(
        "⏸ <b>Auto Trading PAUSED</b>\n"
        "บอทยังวิเคราะห์และแจ้งสัญญาณ แต่ไม่เปิด trade อัตโนมัติ\n"
        "พิมพ์ /start เพื่อเปิดใหม่"
    )


def _cmd_quit(username: str):
    store.stop_bot(by=username)
    _send("🛑 <b>Bot stopped</b>\nหยุดการทำงานแล้ว — พิมพ์ /start เพื่อรีสตาร์ท")


def _cmd_status():
    rs     = get_risk_summary()
    status = store.get_status()
    auto   = "✅ เปิด" if status["trading_enabled"] else "⏸ หยุด"
    bot_on = "🟢 Running" if status["running"] else "🔴 Stopped"

    open_syms = [s for s in SYMBOLS if store.position_exists(s)]
    pos_str   = ", ".join(open_syms) if open_syms else "—"

    _send(
        f"📊 <b>Bot Status</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🤖 Bot       : {bot_on}\n"
        f"⚡ Auto Trade: {auto}\n"
        f"─────────────────\n"
        f"💰 Balance   : <code>{rs.get('balance', '?')}</code>\n"
        f"📈 Equity    : <code>{rs.get('equity', '?')}</code>\n"
        f"📉 Drawdown  : <code>{rs.get('drawdown_pct', '?')}%</code>\n"
        f"💔 Daily Loss: <code>{rs.get('daily_loss_pct', '?')}%</code>\n"
        f"🔁 Loss Streak: <code>{rs.get('consec_losses', '?')}</code>\n"
        f"─────────────────\n"
        f"📌 Open Positions: <code>{pos_str}</code>"
    )


def _cmd_symbols():
    lines   = ["📋 <b>Symbol Status</b>\n━━━━━━━━━━━━━━━━"]
    trading = store.is_trading_enabled()

    for sym, cfg in SYMBOLS.items():
        enabled = store.is_symbol_enabled(sym)
        has_pos = store.position_exists(sym)
        mode    = store.get_symbol_mode(sym)

        if trading and enabled:
            icon = "✅ Auto"
        elif enabled:
            icon = "⏸ Alert"
        else:
            icon = "⛔ Off"

        pos_str  = "  📌" if has_pos else ""
        mode_str = f"  <code>[{mode}]</code>" if mode != "auto" else ""
        lines.append(f"{icon}  <code>{sym}</code>  ({cfg['label']}){mode_str}{pos_str}")

    lines.append("")
    lines.append("/enable SYMBOL — เปิด auto trade")
    lines.append("/disable SYMBOL — เปิดแค่ alert")
    lines.append("/setmode SYMBOL MODE — ตั้ง entry type")
    _send("\n".join(lines))


def _cmd_enable(arg: str, username: str):
    if not arg:
        _send("❓ ระบุ symbol: <code>/enable XAUUSDm</code>")
        return
    sym = _resolve_symbol(arg)
    if sym is None:
        _send(f"❌ ไม่พบ symbol <code>{arg}</code>  ดู /symbols")
        return
    store.enable_symbol(sym, by=username)
    _send(f"✅ <b>{sym}</b> — เปิด auto trade แล้ว")


def _cmd_disable(arg: str, username: str):
    if not arg:
        _send("❓ ระบุ symbol: <code>/disable XAUUSDm</code>")
        return
    sym = _resolve_symbol(arg)
    if sym is None:
        _send(f"❌ ไม่พบ symbol <code>{arg}</code>  ดู /symbols")
        return
    store.disable_symbol(sym, reason="Disabled by user", by=username)
    _send(f"⏸ <b>{sym}</b> — ปิด auto trade แล้ว")


def _cmd_signal(arg: str):
    """Run on-demand signal analysis for a symbol."""
    sym = _resolve_symbol(arg) if arg else list(SYMBOLS.keys())[0]
    if sym is None:
        _send(f"❌ ไม่พบ symbol <code>{arg}</code>  ดู /symbols")
        return
    cfg = SYMBOLS[sym]

    _send(f"🔍 กำลังวิเคราะห์ <code>{sym}</code>…")

    ask, bid = get_latest_price(sym)
    if ask == 0:
        _send(f"❌ ดึงราคา {sym} ไม่ได้ในขณะนี้")
        return

    df_h4  = get_candles(sym, "H4",  count=100)
    df_h1  = get_candles(sym, "H1",  count=100)
    df_m15 = get_candles(sym, "M15", count=100)

    if any(d is None for d in [df_h4, df_h1, df_m15]):
        _send(f"❌ โหลดข้อมูลกราฟ <code>{sym}</code> ไม่สำเร็จ")
        return

    signal, info = generate_signal(df_h4, df_h1, df_m15, cfg, ask=ask, bid=bid)

    icon   = "🟢" if signal == "BUY" else ("🔴" if signal == "SELL" else "⬜")
    price  = ask if signal == "BUY" else bid
    conf   = ", ".join(info.get("confluence", [])) or "—"
    m15sig = ", ".join(info.get("m15_signals", [])) or "—"

    lines = [
        f"{icon} <b>{signal}</b>  <code>{sym}</code>",
        f"━━━━━━━━━━━━━━━━",
        f"💰 Price      : <code>{price}</code>",
        f"🏗 H4 Trend   : <code>{info.get('h4_structure', '?')}</code>",
        f"📡 H4 EMA bias: <code>{info.get('h4_ema_bias', '?')}</code>",
    ]

    if signal in ("BUY", "SELL"):
        lines += [
            f"─────────────────",
            f"🎯 Entry Type : <code>{info.get('entry_type', '?')}</code>",
            f"🔗 Zone conf  : <code>{conf}</code>",
            f"📊 M15 signal : <code>{m15sig}</code>",
            f"📐 RSI (M15)  : <code>{info.get('m15_rsi', '?')}</code>",
            f"─────────────────",
            f"🛑 SL         : <code>{info.get('sl', '?')}</code>",
            f"🎯 TP         : <code>{info.get('tp', '?')}</code>",
            f"📐 R:R        : <code>{info.get('rr', '?')}</code>",
        ]
    else:
        lines.append(f"💡 <i>{info.get('reason', '—')}</i>")

    _send("\n".join(lines))


def _cmd_positions():
    """Show all currently open positions."""
    lines = ["📌 <b>Open Positions</b>\n━━━━━━━━━━━━━━━━"]
    found = False

    for sym in SYMBOLS:
        pos = store.get_open_position(sym)
        if not pos:
            continue
        found = True
        sig    = pos.get("signal", "?")
        icon   = "🟢" if sig == "BUY" else "🔴"
        entry  = pos.get("entry_price", "?")
        sl     = pos.get("sl", "?")
        tp     = pos.get("tp", "?")
        lot    = pos.get("lot", "?")
        atr    = pos.get("atr_at_open", "?")
        lines.append(
            f"{icon} <b>{sym}</b>  {sig}\n"
            f"   Entry: <code>{entry}</code>   SL: <code>{sl}</code>   TP: <code>{tp}</code>\n"
            f"   Lot: <code>{lot}</code>   ATR: <code>{atr}</code>"
        )

    if not found:
        lines.append("ไม่มี open position ในขณะนี้")
    else:
        lines.append("\n/close SYMBOL — ปิดเฉพาะ symbol")
        lines.append("/close — ปิดทั้งหมด")

    _send("\n".join(lines))


def _cmd_close(arg: str):
    resolved = _resolve_symbol(arg) if arg else None
    if arg and resolved is None:
        _send(f"❌ ไม่พบ symbol <code>{arg}</code>  ดู /symbols")
        return
    if resolved:
        if not store.position_exists(resolved):
            _send(f"ℹ️  <code>{resolved}</code> ไม่มี position เปิดอยู่")
            return
        close_position(resolved, comment="manual_close")
        _send(f"🔒 ส่งคำสั่งปิด position <b>{resolved}</b> แล้ว")
    else:
        open_syms = [s for s in SYMBOLS if store.position_exists(s)]
        if not open_syms:
            _send("ℹ️  ไม่มี position เปิดอยู่เลย")
            return
        close_all(comment="manual_close")
        _send(f"🔒 ส่งคำสั่งปิดทุก position แล้ว ({', '.join(open_syms)})")


def _cmd_chart(parts: list):
    """
    /chart [SYMBOL] [TF]
    TF: M15 (default) | H1 | H4
    """
    # Parse args: /chart, /chart GOLD, /chart XAUUSDm H1
    sym = list(SYMBOLS.keys())[0]
    tf  = "M15"

    for part in parts[1:]:
        if part.upper() in _VALID_TF:
            tf = part.upper()
        else:
            resolved = _resolve_symbol(part)
            if resolved:
                sym = resolved

    _send(f"📈 กำลังสร้างกราฟ <code>{sym} {tf}</code>…")
    df = get_candles(sym, tf, count=120)
    if df is not None:
        img = generate_chart(df, symbol=sym, timeframe=tf)
        if img:
            tg.send_chart_bytes(img, caption=f"📊 {sym} {tf}")
            return
    _send(f"⚠️ ไม่สามารถสร้างกราฟ <code>{sym} {tf}</code>")


def _cmd_setmode(parts: list, username: str):
    """
    /setmode SYMBOL MODE
    MODE: auto | pullback | pullback_sell | breakout | range
    """
    if len(parts) < 3:
        _send(
            "❓ ใช้งาน: <code>/setmode SYMBOL MODE</code>\n"
            "MODE ที่ใช้ได้:\n"
            "  <code>auto</code>         — ระบบเลือกเอง (แนะนำ)\n"
            "  <code>pullback</code>     — Buy pullback เท่านั้น\n"
            "  <code>pullback_sell</code>— Sell pullback เท่านั้น\n"
            "  <code>breakout</code>     — Breakout retest เท่านั้น\n"
            "  <code>range</code>        — Range support เท่านั้น"
        )
        return

    sym = _resolve_symbol(parts[1])
    mode = parts[2].lower()

    if sym is None:
        _send(f"❌ ไม่พบ symbol <code>{parts[1]}</code>  ดู /symbols")
        return

    ok = store.set_symbol_mode(sym, mode)
    if ok:
        mode_desc = {
            "auto":         "ระบบเลือกเอง",
            "pullback":     "Buy Pullback เท่านั้น",
            "pullback_sell":"Sell Pullback เท่านั้น",
            "breakout":     "Breakout Retest เท่านั้น",
            "range":        "Range Support เท่านั้น",
        }.get(mode, mode)
        _send(f"✅ <b>{sym}</b> mode = <code>{mode}</code>\n({mode_desc})")
    else:
        _send(
            f"❌ mode <code>{mode}</code> ไม่ถูกต้อง\n"
            f"ใช้ได้: <code>auto</code> | <code>pullback</code> | "
            f"<code>pullback_sell</code> | <code>breakout</code> | <code>range</code>"
        )


def _cmd_mode(arg: str):
    if not arg:
        _send("❓ ระบุ symbol: <code>/mode XAUUSDm</code>")
        return
    sym = _resolve_symbol(arg)
    if sym is None:
        _send(f"❌ ไม่พบ symbol <code>{arg}</code>  ดู /symbols")
        return
    mode = store.get_symbol_mode(sym)
    _send(f"🎯 <b>{sym}</b> entry mode = <code>{mode}</code>")


def _cmd_setbalance(parts: list):
    try:
        bal = float(parts[1])
        eq  = float(parts[2]) if len(parts) > 2 else bal
        store.set_account_snapshot({"balance": bal, "equity": eq,
                                    "margin": 0, "currency": "USD"})
        _send(f"💰 Balance อัพเดทเป็น <code>{bal}</code>  Equity: <code>{eq}</code>")
    except (IndexError, ValueError):
        _send("❓ ใช้งาน: <code>/setbalance 10000.00 [equity]</code>")


def _cmd_help():
    _send(
        "📖 <b>คำสั่งทั้งหมด</b>\n\n"
        "<b>Bot control:</b>\n"
        "/start              — เปิด auto trade ทุก symbol\n"
        "/stop               — หยุด auto trade (แจ้งสัญญาณต่อ)\n"
        "/quit               — ปิด bot\n\n"
        "<b>ข้อมูล:</b>\n"
        "/status             — สถานะ bot + risk summary\n"
        "/symbols            — สถานะทุก symbol\n"
        "/positions          — ดู open positions ทั้งหมด\n"
        "/signal [SYMBOL]    — วิเคราะห์สัญญาณตอนนี้\n"
        "/chart [SYMBOL] [TF]— ดูกราฟ (TF: M15/H1/H4)\n\n"
        "<b>Symbol:</b>\n"
        "/enable SYMBOL      — เปิด auto trade\n"
        "/disable SYMBOL     — เปิดแค่ alert\n"
        "/close [SYMBOL]     — ปิด position\n"
        "/mode SYMBOL        — ดู entry mode ปัจจุบัน\n"
        "/setmode SYMBOL MODE— ตั้ง entry type\n"
        "  MODE: auto | pullback | pullback_sell | breakout | range\n\n"
        "<b>Account:</b>\n"
        "/setbalance BAL [EQ]— อัพเดท balance ใน bot\n\n"
        "<i>ตัวอย่าง:</i>\n"
        "<code>/signal XAUUSDm</code>\n"
        "<code>/chart XAUUSDm H1</code>\n"
        "<code>/setmode XAUUSDm pullback</code>"
    )


# ── Main dispatcher ───────────────────────────────────────────

def _handle(text: str, username: str):
    parts = text.strip().split()
    cmd   = parts[0].lower().split("@")[0]
    arg   = parts[1] if len(parts) > 1 else ""

    if cmd == "/start":
        _cmd_start(username)
    elif cmd == "/stop":
        _cmd_stop(username)
    elif cmd == "/quit":
        _cmd_quit(username)
    elif cmd == "/status":
        _cmd_status()
    elif cmd == "/symbols":
        _cmd_symbols()
    elif cmd == "/enable":
        _cmd_enable(arg, username)
    elif cmd == "/disable":
        _cmd_disable(arg, username)
    elif cmd == "/signal":
        _cmd_signal(arg)
    elif cmd == "/positions":
        _cmd_positions()
    elif cmd == "/close":
        _cmd_close(arg)
    elif cmd == "/chart":
        _cmd_chart(parts)
    elif cmd == "/setmode":
        _cmd_setmode(parts, username)
    elif cmd == "/mode":
        _cmd_mode(arg)
    elif cmd == "/setbalance":
        _cmd_setbalance(parts)
    elif cmd in ("/help", "/commands", "/?"):
        _cmd_help()
    else:
        _send(f"❓ ไม่รู้จักคำสั่ง <code>{cmd}</code>\nพิมพ์ /help ดูคำสั่งทั้งหมด")


# ── Vercel HTTP handler ───────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            update = json.loads(body)
        except json.JSONDecodeError:
            self._reply(400, "Bad JSON")
            return

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

        # Always 200 fast — Telegram retries on non-200
        self._reply(200, "ok")

    def _reply(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass
