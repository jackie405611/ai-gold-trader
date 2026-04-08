# ============================================================
#  command_listener.py  —  Telegram Commands V3
#  คำสั่งใหม่: /enable SYMBOL, /disable SYMBOL, /symbols
# ============================================================
import threading, requests, time
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS
import bot_controller as ctrl

_BASE        = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
_last_update = 0


def _send(text):
    try:
        requests.post(f"{_BASE}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=8)
    except Exception as e:
        print(f"[Cmd] send error: {e}")


def _handle(text, username):
    parts = text.strip().split()
    cmd   = parts[0].lower()
    arg   = parts[1].upper() if len(parts) > 1 else ""

    # ── Bot-level commands ──────────────────────────────────
    if cmd == "/start":
        ctrl.enable_trading(by=username)
        _send("✅ <b>Auto Trading ENABLED</b>\nบอทจะเปิด trade อัตโนมัติสำหรับทุก symbol ที่เปิดอยู่")

    elif cmd == "/stop":
        ctrl.disable_trading(reason="Paused by user", by=username)
        _send("⏸ <b>Auto Trading PAUSED</b>\nบอทยังวิเคราะห์และแจ้งสัญญาณ แต่ไม่เปิด trade\nพิมพ์ /start เพื่อเปิดใหม่")

    elif cmd == "/quit":
        ctrl.stop_bot(by=username)
        _send("🛑 <b>Bot shutting down...</b>")

    # ── Symbol-level commands ───────────────────────────────
    elif cmd == "/enable":
        if not arg:
            _send("❓ ระบุ symbol ด้วย เช่น <code>/enable EURUSDm</code>")
            return
        ok = ctrl.enable_symbol(arg, by=username)
        if ok:
            _send(f"✅ <b>{arg}</b> — เปิด auto trade แล้ว")
        else:
            _send(f"❌ ไม่พบ symbol <code>{arg}</code>\nดู /symbols สำหรับรายชื่อ")

    elif cmd == "/disable":
        if not arg:
            _send("❓ ระบุ symbol ด้วย เช่น <code>/disable EURUSDm</code>")
            return
        ok = ctrl.disable_symbol(arg, reason="Disabled by user", by=username)
        if ok:
            _send(f"⏸ <b>{arg}</b> — ปิด auto trade แล้ว (ยังแจ้งสัญญาณ)")
        else:
            _send(f"❌ ไม่พบ symbol <code>{arg}</code>")

    elif cmd == "/symbols":
        lines = ["📋 <b>Symbol Status</b>\n━━━━━━━━━━━━━━━━"]
        for sym, cfg in SYMBOLS.items():
            state   = ctrl.is_symbol_enabled(sym)
            trading = ctrl.is_trading_enabled()
            if trading and state:
                icon = "✅ Auto"
            elif state:
                icon = "⏸ Alert"
            else:
                icon = "⛔ Off"
            lines.append(f"{icon}  <code>{sym}</code>  ({cfg['label']})")
        lines.append("\n/enable SYMBOL — เปิด auto trade")
        lines.append("/disable SYMBOL — เปิดแค่ alert")
        _send("\n".join(lines))

    # ── Info commands ───────────────────────────────────────
    elif cmd == "/status":
        from risk_manager import get_risk_summary
        rs    = get_risk_summary()
        state = ctrl.get_status()
        auto  = "✅ ON" if state["trading_enabled"] else "⏸ OFF"
        _send(
            f"📊 <b>Bot Status</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🤖 Auto Trade : {auto}\n"
            f"💰 Balance    : <code>{rs.get('balance','?')}</code>\n"
            f"📈 Equity     : <code>{rs.get('equity','?')}</code>\n"
            f"📉 DD         : <code>{rs.get('drawdown_pct','?')}%</code>\n"
            f"💔 Daily Loss : <code>{rs.get('daily_loss_pct','?')}%</code>\n"
            f"🔁 Loss Streak: <code>{rs.get('consec_losses','?')}</code>\n\n"
            f"พิมพ์ /symbols ดูสถานะรายคู่"
        )

    elif cmd == "/close":
        from trade_manager import close_all_positions
        if arg and arg in SYMBOLS:
            close_all_positions(arg, comment="manual_close")
            _send(f"🔒 ปิด position <b>{arg}</b> แล้ว")
        else:
            for sym in SYMBOLS:
                close_all_positions(sym, comment="manual_close")
            _send("🔒 ปิด position ทั้งหมดแล้ว")

    elif cmd == "/chart":
        from chart_generator import generate_chart
        from telegram_bot    import send_chart
        sym = arg if arg in SYMBOLS else list(SYMBOLS.keys())[0]
        chart = generate_chart(symbol=sym)
        if chart:
            send_chart(chart, f"📊 {sym}", blocking=True)
        else:
            _send(f"⚠️ ไม่สามารถสร้างกราฟ {sym}")

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
            "/close [SYMBOL] — ปิด position (ทั้งหมด หรือเฉพาะ symbol)\n"
            "/chart [SYMBOL] — ดูกราฟ"
        )


def _poll_loop():
    global _last_update
    print("[Cmd] Listener started")
    while ctrl.is_bot_running():
        try:
            resp = requests.get(f"{_BASE}/getUpdates",
                params={"offset": _last_update + 1, "timeout": 2}, timeout=10)
            if resp.status_code != 200:
                time.sleep(3); continue
            for upd in resp.json().get("result", []):
                _last_update = upd["update_id"]
                msg = upd.get("message") or upd.get("edited_message")
                if not msg: continue
                if str(msg["chat"]["id"]) != str(TELEGRAM_CHAT_ID): continue
                text = msg.get("text", "")
                user = msg.get("from", {}).get("username", "unknown")
                if text.startswith("/"):
                    print(f"[Cmd] @{user}: {text}")
                    _handle(text, user)
        except Exception as e:
            print(f"[Cmd] Poll error: {e}")
        time.sleep(2)
    print("[Cmd] Listener stopped")


def start_listener():
    t = threading.Thread(target=_poll_loop, daemon=True, name="cmd-listener")
    t.start()
    return t
