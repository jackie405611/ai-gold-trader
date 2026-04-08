# ============================================================
#  lib/telegram_notify.py  —  Telegram notifications (Vercel)
#  Adapted from telegram_bot.py: threading removed (serverless).
# ============================================================
import os, requests
from lib.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def _post(endpoint: str, **kwargs) -> bool:
    for attempt in range(2):
        try:
            r = requests.post(f"{_BASE}/{endpoint}", timeout=12, **kwargs)
            if r.status_code == 200:
                return True
            print(f"[TG] ⚠️  {endpoint} attempt {attempt+1}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[TG] ⚠️  {endpoint} attempt {attempt+1}: {e}")
    return False


def send(text: str) -> bool:
    return _post("sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})


def send_chart_bytes(image_bytes: bytes, caption: str = "") -> bool:
    return _post("sendPhoto",
        data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("chart.png", image_bytes, "image/png")})


# ── Named notification helpers ────────────────────────────────

def notify_bot_start(version: str = "V3") -> None:
    send(f"🚀 <b>AI Gold Trader {version} Started</b>\n"
         f"Cloud mode — no MT5 required.\n"
         f"พิมพ์ /status ดูสถานะ")


def notify_trade_signal(symbol: str, signal: str, info: dict,
                        ask: float, bid: float, sl: float, tp: float,
                        lot: float) -> None:
    icon  = "🟢" if signal == "BUY" else "🔴"
    price = ask if signal == "BUY" else bid
    send(
        f"{icon} <b>{signal}</b>  <code>{symbol}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Entry : <code>{price}</code>\n"
        f"🛑 SL    : <code>{sl}</code>\n"
        f"🎯 TP    : <code>{tp}</code>\n"
        f"📦 Lot   : <code>{lot}</code>\n"
        f"📊 Regime: {info.get('regime','?')}  ADX: {info.get('adx','?')}\n"
        f"📈 M5 RSI: {info.get('m5_rsi','?')}  "
        f"M1 RSI: {info.get('m1_rsi','?')}\n"
        f"⚠️  <i>Signal-only — เปิด trade เองใน MT5</i>"
    )


def notify_trade_executed(symbol: str, signal: str, price: float,
                          sl: float, tp: float, lot: float) -> None:
    icon = "🟢" if signal == "BUY" else "🔴"
    send(
        f"{icon} <b>Trade Opened (MetaAPI)</b>  <code>{symbol}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Entry : <code>{price}</code>\n"
        f"🛑 SL    : <code>{sl}</code>\n"
        f"🎯 TP    : <code>{tp}</code>\n"
        f"📦 Lot   : <code>{lot}</code>"
    )


def notify_risk_event(reason: str) -> None:
    send(f"🚨 <b>Risk Gate Triggered</b>\n{reason}\nAuto trading paused.")


def notify_no_trade(symbol: str, signal: str, reason: str) -> None:
    send(f"ℹ️  <code>{symbol}</code> signal <b>{signal}</b> — {reason}")
