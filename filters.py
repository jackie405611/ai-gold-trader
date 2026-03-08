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
    """
    ตรวจ session สำหรับแต่ละ symbol แยกกัน
    - sessions = [(0, 24)] → เปิดตลอด 24 ชั่วโมง (crypto)
    - sessions = [(7, 12), (13, 17)] → เปิดเฉพาะช่วงเวลา (forex/gold)
    - ตรวจ weekend สำหรับ non-crypto ด้วย
    """
    if not USE_SESSION_FILTER:
        return True

    now      = datetime.now(timezone.utc)
    hour     = now.hour
    weekday  = now.weekday()   # 0=Mon … 5=Sat, 6=Sun
    sessions = cfg.get("sessions", [(0, 24)])
    is_24h   = sessions == [(0, 24)]

    # Crypto (24h) — เปิดทุกวันไม่มีวันหยุด
    if is_24h:
        return True

    # Forex/Gold — ปิดวันเสาร์, ปิดอาทิตย์ก่อน 22:00 UTC
    if weekday == 5:
        return False
    if weekday == 6 and hour < 22:
        return False

    # ตรวจ session window
    for start, end in sessions:
        if start <= hour < end:
            return True

    return False


def market_open():
    """ใช้สำหรับ check แบบ global (deprecated — ใช้ session_ok แทน)"""
    now = datetime.now(timezone.utc)
    return not (now.weekday() == 5 or (now.weekday() == 6 and now.hour < 22))


def position_exists(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if positions and len(positions) > 0:
        print(f"[Filter:{symbol}] ⏸  Position already open")
        return True
    return False
