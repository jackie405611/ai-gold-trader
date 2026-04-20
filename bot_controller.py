# bot_controller.py
import threading
from datetime import datetime, timezone
from config import SYMBOLS


_lock = threading.Lock()

DEFAULT_MODE = "auto"
VALID_MODES = {"auto", "pullback", "breakout", "range"}

_state = {
    "trading_enabled": True,
    "bot_running": True,
    "toggled_at": None,
    "toggled_by": "system",
    "symbols": {sym: cfg["enabled"] for sym, cfg in SYMBOLS.items()},
    "strategy_modes": {
        sym: cfg.get("strategy_mode", DEFAULT_MODE) for sym, cfg in SYMBOLS.items()
    },
}


def is_trading_enabled():
    with _lock:
        return _state["trading_enabled"]


def is_bot_running():
    with _lock:
        return _state["bot_running"]


def get_status():
    with _lock:
        return dict(_state)


def enable_trading(by="user"):
    with _lock:
        _state["trading_enabled"] = True
        _state["toggled_at"] = datetime.now(timezone.utc)
        _state["toggled_by"] = by
        print(f"[Ctrl] ✅ Trading ENABLED by {by}")


def disable_trading(reason="", by="user"):
    with _lock:
        _state["trading_enabled"] = False
        _state["toggled_at"] = datetime.now(timezone.utc)
        _state["toggled_by"] = by
        print(f"[Ctrl] ⏸ Trading DISABLED by {by}: {reason}")


def stop_bot(by="user"):
    with _lock:
        _state["bot_running"] = False
        _state["trading_enabled"] = False
        _state["toggled_by"] = by
        print(f"[Ctrl] STOP by {by}")


def is_symbol_enabled(symbol):
    with _lock:
        return _state["symbols"].get(symbol, False)


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
        print(f"[Ctrl] ⏸ {symbol} DISABLED by {by}: {reason}")
        return True


def should_trade(symbol):
    with _lock:
        return _state["trading_enabled"] and _state["symbols"].get(symbol, False)


def set_strategy_mode(symbol, mode, by="user"):
    mode = (mode or "").lower().strip()
    with _lock:
        if symbol not in _state["strategy_modes"]:
            return False, "unknown_symbol"
        if mode not in VALID_MODES:
            return False, "invalid_mode"
        _state["strategy_modes"][symbol] = mode
        print(f"[Ctrl] 🎯 {symbol} strategy mode = {mode} by {by}")
        return True, mode


def get_strategy_mode(symbol):
    with _lock:
        return _state["strategy_modes"].get(symbol, DEFAULT_MODE)


def get_all_strategy_modes():
    with _lock:
        return dict(_state["strategy_modes"])
