# ============================================================
#  telegram_bot.py  —  Telegram Notifications  (V2)
#  ใหม่: Non-blocking (thread), retry logic, rich message format
# ============================================================
import requests
import threading
from datetime import datetime
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def _post(url, **kwargs):
    """POST พร้อม retry 2 ครั้ง — รันใน thread ย่อย"""
    for attempt in range(2):
        try:
            resp = requests.post(url, timeout=10, **kwargs)
            if resp.status_code == 200:
                return
        except Exception as e:
            print(f"[Telegram] attempt {attempt+1} failed: {e}")


def _async(fn, *args, **kwargs):
    """รัน fn ใน background thread ไม่บล็อก main loop"""
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


# ── Public API ───────────────────────────────────────────────

def send_telegram(msg: str, blocking=False):
    """ส่ง text message"""
    url  = f"{_BASE}/sendMessage"
    data = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       msg,
        "parse_mode": "HTML",
    }
    if blocking:
        _post(url, data=data)
    else:
        _async(_post, url, data=data)


def send_chart(image_path: str, caption="", blocking=False):
    """ส่งรูปภาพ"""
    url = f"{_BASE}/sendPhoto"

    def _send():
        try:
            with open(image_path, "rb") as img:
                _post(url,
                      data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                      files={"photo": img})
        except FileNotFoundError:
            print(f"[Telegram] Chart file not found: {image_path}")

    if blocking:
        _send()
    else:
        _async(_send)


def notify_trade_open(signal, price, sl, tp, lot, atr, regime):
    """แจ้งเปิด trade พร้อมรายละเอียด"""
    emoji = "🟢 BUY" if signal == "BUY" else "🔴 SELL"
    rr    = round(abs(tp - price) / abs(sl - price), 2) if abs(sl - price) > 0 else "-"
    ts    = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    msg = (
        f"<b>{emoji} XAUUSD</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Entry : <code>{price:.2f}</code>\n"
        f"🛡  SL    : <code>{sl:.2f}</code>\n"
        f"🎯 TP    : <code>{tp:.2f}</code>\n"
        f"📦 Lot   : <code>{lot}</code>\n"
        f"📊 ATR   : <code>{atr:.4f}</code>\n"
        f"📈 RR    : <code>1:{rr}</code>\n"
        f"🌐 Regime: <code>{regime}</code>\n"
        f"🕐 Time  : {ts}"
    )
    send_telegram(msg)


def notify_trade_closed(ticket, profit, pnl_pct):
    """แจ้งปิด trade"""
    emoji = "✅ WIN" if profit > 0 else "❌ LOSS"
    msg   = (
        f"<b>{emoji} — Ticket #{ticket}</b>\n"
        f"P&L: <code>{profit:+.2f} USD ({pnl_pct:+.2f}%)</code>"
    )
    send_telegram(msg)


def notify_risk_event(reason):
    """แจ้งเหตุการณ์ risk"""
    send_telegram(f"⛔ <b>RISK EVENT</b>\n{reason}", blocking=True)


def notify_bot_start(version="V2"):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    send_telegram(
        f"🤖 <b>AI Gold Trader {version} Started</b>\n"
        f"Symbol: XAUUSD\n"
        f"Time: {ts}",
        blocking=True
    )
