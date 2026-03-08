# ============================================================
#  risk_manager.py  —  Risk Management V3 (per-symbol aware)
# ============================================================
import MetaTrader5 as mt5
from config import MAX_DD, RISK_PER_TRADE, USE_DYNAMIC_LOT
import threading

_lock  = threading.Lock()
_state = {
    "consecutive_losses": 0,
    "daily_start_balance": None,
    "daily_loss_pct": 0.0,
}

MAX_CONSECUTIVE_LOSS = 3
MAX_DAILY_LOSS_PCT   = 5.0


def check_drawdown():
    acc = mt5.account_info()
    if not acc:
        return True
    dd = (acc.balance - acc.equity) / acc.balance * 100 if acc.balance > 0 else 0
    print(f"[Risk] DD:{dd:.2f}%  Balance:{acc.balance:.2f}  Equity:{acc.equity:.2f}")
    if dd >= MAX_DD:
        print("[Risk] ❌ MAX DD reached")
        return False
    if _state["daily_start_balance"] is None:
        _state["daily_start_balance"] = acc.balance
    daily_loss = (_state["daily_start_balance"] - acc.equity) / _state["daily_start_balance"] * 100
    _state["daily_loss_pct"] = daily_loss
    if daily_loss >= MAX_DAILY_LOSS_PCT:
        print(f"[Risk] ❌ Daily loss {daily_loss:.2f}%")
        return False
    if _state["consecutive_losses"] >= MAX_CONSECUTIVE_LOSS:
        print(f"[Risk] ❌ {MAX_CONSECUTIVE_LOSS} consecutive losses")
        return False
    return True


def calculate_lot(atr, symbol, cfg=None):
    if not USE_DYNAMIC_LOT or not atr:
        return (cfg or {}).get("lot", 0.01)
    sl_mult  = (cfg or {}).get("atr_sl_mult", 1.5)
    acc      = mt5.account_info()
    if not acc:
        return 0.01
    sym_info = mt5.symbol_info(symbol)
    if not sym_info:
        return 0.01
    point       = sym_info.point
    tick_value  = sym_info.trade_tick_value
    sl_points   = (atr * sl_mult) / point
    risk_usd    = acc.balance * (RISK_PER_TRADE / 100)
    lot         = risk_usd / (sl_points * tick_value) if tick_value > 0 else 0.01
    return max(0.01, min(round(lot, 2), 1.0))


def record_trade_result(profit):
    with _lock:
        if profit < 0:
            _state["consecutive_losses"] += 1
        else:
            _state["consecutive_losses"] = 0


def reset_daily():
    with _lock:
        acc = mt5.account_info()
        _state["daily_start_balance"] = acc.balance if acc else None
        _state["daily_loss_pct"]      = 0.0


def get_risk_summary():
    acc = mt5.account_info()
    if not acc:
        return {}
    dd = (acc.balance - acc.equity) / acc.balance * 100 if acc.balance > 0 else 0
    return {
        "balance":        round(acc.balance, 2),
        "equity":         round(acc.equity,  2),
        "drawdown_pct":   round(dd, 2),
        "daily_loss_pct": round(_state["daily_loss_pct"], 2),
        "consec_losses":  _state["consecutive_losses"],
    }
