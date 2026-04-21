# ============================================================
#  lib/telegram_notify.py  —  Telegram notifications (Vercel)
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
         f"พิมพ์ /help ดูคำสั่งทั้งหมด")


def notify_trade_signal(symbol: str, signal: str, info: dict,
                        ask: float, bid: float, sl: float, tp: float,
                        lot: float) -> None:
    icon    = "🟢" if signal == "BUY" else "🔴"
    price   = ask if signal == "BUY" else bid
    rr      = info.get("rr", "?")
    etype   = info.get("entry_type", "?")
    conf    = info.get("confluence", [])
    h4      = info.get("h4_structure", "?")
    m15_sig = info.get("m15_signals", [])
    reason  = info.get("reason", "")

    conf_str = ", ".join(conf) if conf else "—"
    m15_str  = ", ".join(m15_sig) if m15_sig else "—"

    send(
        f"{icon} <b>{signal}</b>  <code>{symbol}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Entry    : <code>{price}</code>\n"
        f"🛑 SL       : <code>{sl}</code>\n"
        f"🎯 TP       : <code>{tp}</code>\n"
        f"📐 R:R      : <code>{rr}</code>\n"
        f"📦 Lot      : <code>{lot}</code>\n"
        f"─────────────────\n"
        f"🏗 H4 Trend : <code>{h4}</code>\n"
        f"🎯 Type     : <code>{etype}</code>\n"
        f"🔗 Zone     : <code>{conf_str}</code>\n"
        f"📊 M15 sig  : <code>{m15_str}</code>\n"
        f"💡 <i>{reason}</i>\n"
        f"⚠️  <i>Signal-only — เปิด trade เองใน MT5</i>"
    )


def notify_trade_executed(symbol: str, signal: str, price: float,
                          sl: float, tp: float, lot: float,
                          info: dict | None = None) -> None:
    icon  = "🟢" if signal == "BUY" else "🔴"
    rr    = (info or {}).get("rr", "?")
    etype = (info or {}).get("entry_type", "")
    send(
        f"{icon} <b>Trade Opened</b>  <code>{symbol}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Entry : <code>{price}</code>\n"
        f"🛑 SL    : <code>{sl}</code>\n"
        f"🎯 TP    : <code>{tp}</code>\n"
        f"📐 R:R   : <code>{rr}</code>\n"
        f"📦 Lot   : <code>{lot}</code>\n"
        + (f"🎯 Type  : <code>{etype}</code>" if etype else "")
    )


def notify_risk_event(reason: str) -> None:
    send(f"🚨 <b>Risk Gate Triggered</b>\n{reason}\nAuto trading paused.")


def notify_no_trade(symbol: str, signal: str, reason: str) -> None:
    send(f"ℹ️  <code>{symbol}</code> signal <b>{signal}</b> — {reason}")
