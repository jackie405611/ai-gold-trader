# ============================================================
#  lib/filters.py  —  Pre-trade Filters (Vercel, no MT5)
# ============================================================
from datetime import datetime, timezone

from lib.config import SYMBOL_MAP, USE_SESSION_FILTER
import lib.state_store as store


def spread_ok(symbol: str, cfg: dict, ask: float, bid: float) -> bool:
    """
    ask/bid : fetched from Twelve Data (estimated).
    point   : from SYMBOL_MAP.
    """
    point  = SYMBOL_MAP[symbol]["point_value"]
    spread = (ask - bid) / point if point > 0 else 0
    if spread > cfg["max_spread"]:
        print(f"[Filter:{symbol}] ❌ Spread {spread:.1f} > {cfg['max_spread']}")
        return False
    print(f"[Filter:{symbol}] ✅ Spread {spread:.1f}")
    return True


def session_ok(cfg: dict) -> bool:
    """Unchanged logic — pure datetime, no MT5."""
    if not USE_SESSION_FILTER:
        return True
    hour     = datetime.now(timezone.utc).hour
    sessions = cfg.get("sessions", [(0, 24)])
    for start, end in sessions:
        if start == 0 and end == 24:
            return True
        if start <= hour < end:
            return True
    print(f"[Filter] ⏸  Outside session (UTC {hour:02d}:xx)")
    return False


def position_exists(symbol: str) -> bool:
    """Check Redis instead of mt5.positions_get()."""
    if store.position_exists(symbol):
        print(f"[Filter:{symbol}] ⏸  Position already open")
        return True
    return False


def market_open() -> bool:
    """Unchanged logic — pure datetime."""
    now     = datetime.now(timezone.utc)
    weekday = now.weekday()   # 0=Mon … 6=Sun
    if weekday == 5:          # Saturday
        return False
    if weekday == 6 and now.hour < 22:  # Sunday before 22:00 UTC
        return False
    return True
