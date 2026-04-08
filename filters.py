# ============================================================
#  filters.py  —  Pre-trade Filters V3 (per-symbol)
# ============================================================
import MetaTrader5 as mt5
from datetime import datetime, timezone
from config import USE_SESSION_FILTER


def spread_ok(symbol, cfg):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False
    info   = mt5.symbol_info(symbol)
    point  = info.point if info else 0.00001
    spread = (tick.ask - tick.bid) / point
    if spread > cfg["max_spread"]:
        print(f"[Filter:{symbol}] ❌ Spread {spread:.1f} > {cfg['max_spread']}")
        return False
    print(f"[Filter:{symbol}] ✅ Spread {spread:.1f}")
    return True


def session_ok(cfg):
    if not USE_SESSION_FILTER:
        return True
    hour = datetime.now(timezone.utc).hour
    sessions = cfg.get("sessions", [(0, 24)])
    # session (0,24) = ตลอดวัน
    for start, end in sessions:
        if start == 0 and end == 24:
            return True
        if start <= hour < end:
            return True
    print(f"[Filter] ⏸  Outside session (UTC {hour:02d}:xx)")
    return False


def position_exists(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if positions and len(positions) > 0:
        print(f"[Filter:{symbol}] ⏸  Position already open")
        return True
    return False


def market_open():
    now     = datetime.now(timezone.utc)
    weekday = now.weekday()
    if weekday == 5:
        return False
    if weekday == 6 and now.hour < 22:
        return False
    return True
