# ============================================================
#  lib/trade_executor.py  —  Trade execution (Vercel)
#  TRADE_MODE=SIGNAL_ONLY  → Telegram alert, manual execution
#  TRADE_MODE=META_API     → Cloud MT5 via MetaAPI REST
# ============================================================
import os
import requests

from lib.config import SYMBOL_MAP
from lib.risk_manager import calculate_lot
import lib.state_store as store
import lib.telegram_notify as tg

TRADE_MODE = os.environ.get("TRADE_MODE", "SIGNAL_ONLY")

# MetaAPI base URL (London region — change if your broker uses a different region)
_META_BASE = "https://mt-client-api-v1.london.agiliumtrade.ai"


# ── Public API ────────────────────────────────────────────────

def open_trade(symbol: str, cfg: dict, signal: str,
               atr: float, ask: float, bid: float) -> dict | None:
    """
    Open a trade or send a signal alert.
    Returns position dict on success, None on failure/signal-only.
    """
    lot    = calculate_lot(atr, symbol, cfg)
    digits = SYMBOL_MAP[symbol]["digits"]
    sl_dist = round(atr * cfg.get("atr_sl_mult", 1.5), digits)
    tp_dist = round(atr * cfg.get("atr_tp_mult", 2.5), digits)

    if signal == "BUY":
        price = ask
        sl    = round(price - sl_dist, digits)
        tp    = round(price + tp_dist, digits)
    else:
        price = bid
        sl    = round(price + sl_dist, digits)
        tp    = round(price - tp_dist, digits)

    if TRADE_MODE == "META_API":
        return _execute_metaapi(symbol, signal, price, sl, tp, lot)
    else:
        return _send_signal_alert(symbol, signal, cfg, atr, ask, bid, price, sl, tp, lot)


def close_position(symbol: str, comment: str = "manual_close") -> None:
    """Close an open position or advise user to do so manually."""
    if TRADE_MODE == "META_API":
        _close_metaapi(symbol)
    else:
        tg.send(f"🔒 <b>Close Signal</b>  <code>{symbol}</code>\n"
                f"⚠️ ปิด position ใน MT5 ด้วยตัวเอง\nเหตุผล: {comment}")
    store.clear_open_position(symbol)


def close_all(comment: str = "manual_close") -> None:
    from lib.config import SYMBOLS
    for sym in SYMBOLS:
        if store.position_exists(sym):
            close_position(sym, comment)


# ── SIGNAL_ONLY mode ──────────────────────────────────────────

def _send_signal_alert(symbol, signal, cfg, atr, ask, bid,
                       price, sl, tp, lot) -> dict | None:
    tg.notify_trade_signal(symbol, signal, {}, ask, bid, sl, tp, lot)
    position = {
        "signal":      signal,
        "entry_price": price,
        "sl":          sl,
        "tp":          tp,
        "lot":         lot,
        "atr_at_open": atr,
    }
    store.set_open_position(symbol, position)
    return position


# ── META_API mode ─────────────────────────────────────────────

def _meta_headers() -> dict:
    return {
        "auth-token":   os.environ.get("META_API_TOKEN", ""),
        "Content-Type": "application/json",
    }

def _account_id() -> str:
    return os.environ.get("META_API_ACCOUNT_ID", "")

def _execute_metaapi(symbol, signal, price, sl, tp, lot) -> dict | None:
    action = "ORDER_TYPE_BUY" if signal == "BUY" else "ORDER_TYPE_SELL"
    payload = {
        "actionType": action,
        "symbol":     symbol,
        "volume":     lot,
        "stopLoss":   sl,
        "takeProfit": tp,
    }
    try:
        resp = requests.post(
            f"{_META_BASE}/users/current/accounts/{_account_id()}/trade",
            json=payload,
            headers=_meta_headers(),
            timeout=15,
        )
        result = resp.json()
        if resp.status_code == 200 and result.get("numericCode") == 10009:
            position = {
                "signal":      signal,
                "entry_price": price,
                "sl":          sl,
                "tp":          tp,
                "lot":         lot,
                "order_id":    result.get("orderId", ""),
            }
            store.set_open_position(symbol, position)
            tg.notify_trade_executed(symbol, signal, price, sl, tp, lot)
            return position
        else:
            print(f"[MetaAPI] ❌ {result}")
            tg.send(f"❌ MetaAPI order failed for <code>{symbol}</code>\n{result}")
            return None
    except Exception as e:
        print(f"[MetaAPI] ❌ {e}")
        return None

def _close_metaapi(symbol: str) -> None:
    pos = store.get_open_position(symbol)
    if not pos:
        return
    # Close by sending opposite order at market (simplified)
    signal  = "SELL" if pos.get("signal") == "BUY" else "BUY"
    action  = "ORDER_TYPE_SELL" if signal == "SELL" else "ORDER_TYPE_BUY"
    payload = {
        "actionType": "POSITION_CLOSE_SYMBOL",
        "symbol":     symbol,
    }
    try:
        requests.post(
            f"{_META_BASE}/users/current/accounts/{_account_id()}/trade",
            json=payload,
            headers=_meta_headers(),
            timeout=15,
        )
    except Exception as e:
        print(f"[MetaAPI] Close error: {e}")
