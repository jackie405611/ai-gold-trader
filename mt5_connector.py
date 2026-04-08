# ============================================================
#  mt5_connector.py  —  MetaTrader 5 Connection  (V2)
# ============================================================
import MetaTrader5 as mt5
import sys


def connect(retries=3):
    """เชื่อมต่อ MT5 พร้อม retry"""
    for attempt in range(1, retries + 1):
        if mt5.initialize():
            info = mt5.terminal_info()
            print(f"[MT5] ✅ Connected — build {info.build if info else '?'}")
            return True
        print(f"[MT5] ❌ Attempt {attempt}/{retries} failed: {mt5.last_error()}")

    print("[MT5] Cannot connect to MetaTrader 5 — exiting")
    sys.exit(1)


def disconnect():
    mt5.shutdown()
    print("[MT5] Disconnected")


def get_price(symbol="XAUUSDm"):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None, None
    return round(tick.ask, 2), round(tick.bid, 2)


def get_account_info():
    acc = mt5.account_info()
    if acc is None:
        return {}
    return {
        "balance":  acc.balance,
        "equity":   acc.equity,
        "margin":   acc.margin,
        "currency": acc.currency,
        "leverage": acc.leverage,
        "server":   acc.server,
    }
