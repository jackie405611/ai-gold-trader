# ============================================================
#  bot_controller.py  —  Shared State V3 (per-symbol switches)
# ============================================================
import threading
from datetime import datetime, timezone
from config import SYMBOLS

_lock = threading.Lock()

_state = {
    "trading_enabled": True,
    "bot_running":     True,
    "toggled_at":      None,
    "toggled_by":      "system",
    # per-symbol enabled state (อ่านจาก config เริ่มต้น)
    "symbols":         {sym: cfg["enabled"] for sym, cfg in SYMBOLS.items()},
}


# ── Bot-level ────────────────────────────────────────────────

def is_trading_enabled():
    with _lock: return _state["trading_enabled"]

def is_bot_running():
    with _lock: return _state["bot_running"]

def get_status():
    with _lock: return dict(_state)

def enable_trading(by="user"):
    with _lock:
        _state["trading_enabled"] = True
        _state["toggled_at"]      = datetime.now(timezone.utc)
        _state["toggled_by"]      = by
    print(f"[Ctrl] ✅ Trading ENABLED by {by}")

def disable_trading(reason="", by="user"):
    with _lock:
        _state["trading_enabled"] = False
        _state["toggled_at"]      = datetime.now(timezone.utc)
        _state["toggled_by"]      = by
    print(f"[Ctrl] ⏸  Trading DISABLED by {by}: {reason}")

def stop_bot(by="user"):
    with _lock:
        _state["bot_running"]     = False
        _state["trading_enabled"] = False
        _state["toggled_by"]      = by
    print(f"[Ctrl] 🛑 STOP by {by}")


# ── Per-symbol ───────────────────────────────────────────────

def is_symbol_enabled(symbol):
    with _lock: return _state["symbols"].get(symbol, False)

def enable_symbol(symbol, by="user"):
    with _lock:
        if symbol not in _state["symbols"]:
            return False
        _state["symbols"][symbol] = True
    print(f"[Ctrl] ✅ {symbol} ENABLED by {by}")
    return True

def disable_symbol(symbol, reason="", by="user"):
    with _lock:
        if symbol not in _state["symbols"]:
            return False
        _state["symbols"][symbol] = False
    print(f"[Ctrl] ⏸  {symbol} DISABLED by {by}: {reason}")
    return True

def should_trade(symbol):
    """
    True = auto trade,  False = alert only
    ต้องผ่านทั้ง 2 เงื่อนไข: bot-level ON และ symbol-level ON
    """
    with _lock:
        return _state["trading_enabled"] and _state["symbols"].get(symbol, False)
