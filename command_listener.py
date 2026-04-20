# ============================================================
#  command_listener.py  —  Telegram Commands V3
# ============================================================
import threading
import time
import requests
import MetaTrader5 as mt5

import bot_controller as ctrl
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS
from data_fetcher import get_candles
from ai_strategy import analyze_signal

_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
_last_update = 0


def _send(text):
    try:
        requests.post(
            f"{_BASE}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=8,
        )
    except Exception as e:
        print(f"[Cmd] send error: {e}")


def _format_signal(sym, sig, info):
    lines = [
        f"📊 <b>{sym}</b>",
        f"signal: <b>{sig}</b>",
        f"strategy: <code>{info.get('strategy', '-')}</code>",
        f"requested_mode: <code>{info.get('requested_mode', '-')}</code>",
        f"effective_mode: <code>{info.get('effective_mode', info.get('requested_mode', '-'))}</code>",
        f"regime: <code>{info.get('regime', '-')}</code>",
        f"bias: <code>{info.get('bias', '-')}</code>",
        f"zone: <code>{info.get('zone_low', '-')} - {info.get('zone_high', '-')}</code>",
        f"confirmed: <code>{info.get('confirmed', False)}</code>",
        f"reason: <code>{info.get('reason', '-')}</code>",
    ]

    if sig in ("BUY", "SELL"):
        lines.extend([
            f"entry: <code>{info.get('entry')}</code>",
            f"sl: <code>{info.get('sl')}</code>",
            f"tp: <code>{info.get('tp')}</code>",
            f"rr: <code>{info.get('rr')}</code>",
        ])

    return "\n".join(lines)


def _handle(text, username):
    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""
    arg1 = parts[1].upper() if len(parts) > 1 else ""
    arg2 = parts[2].lower() if len(parts) > 2 else ""

    if cmd == "/start":
        ctrl.enable_trading(by=username)
        _send("✅ <b>Auto Trading ENABLED</b>\nบอทจะเปิด trade อัตโนมัติสำหรับทุก symbol ที่เปิดอยู่")

    elif cmd == "/stop":
        ctrl.disable_trading(reason="Paused by user", by=username)
        _send("⏸ <b>Auto Trading PAUSED</b>\nบอทยังวิเคราะห์และแจ้งสัญญาณ แต่ไม่เปิด trade\nพิมพ์ /start เพื่อเปิดใหม่")

    elif cmd == "/quit":
        ctrl.stop_bot(by=username)
        _send("🛑 <b>Bot shutting down...</b>")

    elif cmd == "/enable":
        if not arg1:
            _send("❓ ระบุ symbol ด้วย เช่น <code>/enable XAUUSDm</code>")
            return
        ok = ctrl.enable_symbol(arg1, by=username)
        if ok:
            _send(f"✅ <b>{arg1}</b> — เปิด auto trade แล้ว")
        else:
            _send(f"❌ ไม่พบ symbol <code>{arg1}</code>\nดู /symbols สำหรับรายชื่อ")

    elif cmd == "/disable":
        if not arg1:
            _send("❓ ระบุ symbol ด้วย เช่น <code>/disable XAUUSDm</code>")
            return
        ok = ctrl.disable_symbol(arg1, reason="Disabled by user", by=username)
        if ok:
            _send(f"⏸ <b>{arg1}</b> — ปิด auto trade แล้ว (ยังแจ้งสัญญาณ)")
        else:
            _send(f"❌ ไม่พบ symbol <code>{arg1}</code>")

    elif cmd == "/symbols":
        lines = ["📋 <b>Symbol Status</b>", "━━━━━━━━━━━━━━━━"]
        for sym, cfg in SYMBOLS.items():
            state = ctrl.is_symbol_enabled(sym)
            trading = ctrl.is_trading_enabled()
            mode = ctrl.get_strategy_mode(sym)

            if trading and state:
                icon = "✅ Auto"
            elif state:
                icon = "⏸ Alert"
            else:
                icon = "⛔ Off"

            lines.append(f"{icon} <code>{sym}</code> ({cfg['label']}) mode=<code>{mode}</code>")

        lines.append("")
        lines.append("/enable SYMBOL — เปิด auto trade")
        lines.append("/disable SYMBOL — ปิด auto trade")
        lines.append("/mode SYMBOL — ดู strategy mode")
        lines.append("/setmode SYMBOL MODE — ตั้ง strategy mode")
        _send("\n".join(lines))

    elif cmd == "/mode":
        if not arg1:
            _send("❓ ใช้แบบนี้ <code>/mode XAUUSDm</code>")
            return
        if arg1 not in SYMBOLS:
            _send(f"❌ ไม่พบ symbol <code>{arg1}</code>")
            return

        mode = ctrl.get_strategy_mode(arg1)
        _send(f"🎯 <b>{arg1}</b> mode = <code>{mode}</code>")

    elif cmd == "/setmode":
        if not arg1 or not arg2:
            _send(
                "❓ ใช้แบบนี้ <code>/setmode XAUUSDm auto</code>\n"
                "โหมดที่ใช้ได้: <code>auto</code>, <code>pullback</code>, <code>breakout</code>, <code>range</code>"
            )
            return

        ok, msg = ctrl.set_strategy_mode(arg1, arg2, by=username)
        if ok:
            _send(f"✅ <b>{arg1}</b> strategy mode = <code>{msg}</code>")
        else:
            if msg == "invalid_mode":
                _send(
                    "❌ mode ไม่ถูกต้อง\n"
                    "ใช้ได้: <code>auto</code>, <code>pullback</code>, <code>breakout</code>, <code>range</code>"
                )
            else:
                _send(f"❌ ไม่พบ symbol <code>{arg1}</code>")

    elif cmd == "/signal":
        sym = arg1 if arg1 in SYMBOLS else list(SYMBOLS.keys())[0]
        mode = arg2 if arg2 else ctrl.get_strategy_mode(sym)

        df_h1 = get_candles(sym, mt5.TIMEFRAME_H1)
        df_m15 = get_candles(sym, mt5.TIMEFRAME_M15)
        df_m5 = get_candles(sym, mt5.TIMEFRAME_M5)
        df_m1 = get_candles(sym, mt5.TIMEFRAME_M1)

        if any(x is None for x in [df_h1, df_m15, df_m5, df_m1]):
            _send(f"⚠️ โหลดข้อมูลกราฟ <code>{sym}</code> ไม่สำเร็จ")
            return

        sig, info = analyze_signal(
            df_h1=df_h1,
            df_m15=df_m15,
            df_m5=df_m5,
            df_m1=df_m1,
            cfg=SYMBOLS[sym],
            mode=mode,
        )
        _send(_format_signal(sym, sig, info))

    elif cmd == "/status":
        from risk_manager import get_risk_summary

        rs = get_risk_summary()
        state = ctrl.get_status()
        auto = "✅ ON" if state["trading_enabled"] else "⏸ OFF"

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

        if arg1 and arg1 in SYMBOLS:
            close_all_positions(arg1, comment="manual_close")
            _send(f"🔒 ปิด position <b>{arg1}</b> แล้ว")
        else:
            for sym in SYMBOLS:
                close_all_positions(sym, comment="manual_close")
            _send("🔒 ปิด position ทั้งหมดแล้ว")

    elif cmd == "/chart":
        from chart_generator import generate_chart
        from telegram_bot import send_chart

        sym = arg1 if arg1 in SYMBOLS else list(SYMBOLS.keys())[0]
        chart = generate_chart(symbol=sym)
        if chart:
            send_chart(chart, f"📊 {sym}", blocking=True)
        else:
            _send(f"⚠️ ไม่สามารถสร้างกราฟ {sym}")

    else:
        _send(
            "❓ <b>คำสั่งที่ใช้ได้</b>\n\n"
            "<b>Bot level:</b>\n"
            "/start — เปิด auto trade ทุก symbol\n"
            "/stop — หยุด auto trade (แจ้งสัญญาณต่อ)\n"
            "/quit — ปิด bot\n"
            "/status — ดูสถานะรวม\n"
            "/symbols — ดูสถานะทุก symbol\n\n"
            "<b>Strategy:</b>\n"
            "/signal [SYMBOL] [MODE] — วิเคราะห์สัญญาณตอนนี้\n"
            "/mode SYMBOL — ดู mode ปัจจุบัน\n"
            "/setmode SYMBOL MODE — ตั้งโหมด strategy\n"
            "MODE: auto | pullback | breakout | range\n\n"
            "<b>Symbol level:</b>\n"
            "/enable SYMBOL — เปิด auto trade symbol นั้น\n"
            "/disable SYMBOL — ปิด auto trade symbol นั้น\n"
            "/close [SYMBOL] — ปิด position (ทั้งหมด หรือเฉพาะ symbol)\n"
            "/chart [SYMBOL] — ดูกราฟ"
        )


def _poll_loop():
    global _last_update
    print("[Cmd] Listener started")

    while ctrl.is_bot_running():
        try:
            resp = requests.get(
                f"{_BASE}/getUpdates",
                params={"offset": _last_update + 1, "timeout": 2},
                timeout=10,
            )

            if resp.status_code != 200:
                time.sleep(3)
                continue

            for upd in resp.json().get("result", []):
                _last_update = upd["update_id"]
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue

                if str(msg["chat"]["id"]) != str(TELEGRAM_CHAT_ID):
                    continue

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
