# ============================================================
#  lib/state_store.py  —  Upstash Redis state wrapper
#  Replaces bot_controller.py + in-memory risk state
# ============================================================
import os, json
from datetime import date
from upstash_redis import Redis

from lib.config import SYMBOLS


def _r() -> Redis:
    return Redis(
        url=os.environ["KV_REST_API_URL"],
        token=os.environ["KV_REST_API_TOKEN"],
    )


# ── Bot control ───────────────────────────────────────────────

def is_bot_running() -> bool:
    return (_r().get("bot:running") or "1") == "1"

def stop_bot(by: str = "system") -> None:
    _r().set("bot:running", "0")

def is_trading_enabled() -> bool:
    return (_r().get("bot:trading_enabled") or "1") == "1"

def enable_trading(by: str = "user") -> None:
    _r().set("bot:trading_enabled", "1")

def disable_trading(reason: str = "", by: str = "user") -> None:
    _r().set("bot:trading_enabled", "0")

def get_status() -> dict:
    r = _r()
    return {
        "running":          (r.get("bot:running") or "1") == "1",
        "trading_enabled":  (r.get("bot:trading_enabled") or "1") == "1",
    }


# ── Per-symbol control ────────────────────────────────────────

def is_symbol_enabled(symbol: str) -> bool:
    val = _r().get(f"symbol:{symbol}:enabled")
    if val is None:
        # Default from config
        return SYMBOLS.get(symbol, {}).get("enabled", False)
    return val == "1"

def enable_symbol(symbol: str, by: str = "user") -> bool:
    if symbol not in SYMBOLS:
        return False
    _r().set(f"symbol:{symbol}:enabled", "1")
    return True

def disable_symbol(symbol: str, reason: str = "", by: str = "user") -> bool:
    if symbol not in SYMBOLS:
        return False
    _r().set(f"symbol:{symbol}:enabled", "0")
    return True

def should_trade(symbol: str) -> bool:
    return is_trading_enabled() and is_symbol_enabled(symbol)


# ── Open positions ────────────────────────────────────────────

def position_exists(symbol: str) -> bool:
    return _r().exists(f"position:{symbol}:open") > 0

def get_open_position(symbol: str) -> dict | None:
    raw = _r().get(f"position:{symbol}:open")
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw

def set_open_position(symbol: str, data: dict) -> None:
    _r().set(f"position:{symbol}:open", json.dumps(data))

def clear_open_position(symbol: str) -> None:
    _r().delete(f"position:{symbol}:open")


# ── Risk state ────────────────────────────────────────────────

def get_risk_state() -> dict:
    r = _r()
    raw = r.hgetall("risk:state") or {}
    return {
        "consecutive_losses":  int(raw.get("consecutive_losses", 0)),
        "daily_start_balance": float(raw.get("daily_start_balance", 0)),
        "daily_loss_pct":      float(raw.get("daily_loss_pct", 0)),
        "last_reset_date":     raw.get("last_reset_date", ""),
    }

def update_risk_state(patch: dict) -> None:
    str_patch = {k: str(v) for k, v in patch.items()}
    _r().hset("risk:state", values=str_patch)

def record_trade_result(profit: float) -> None:
    r = _r()
    current = int(r.hget("risk:state", "consecutive_losses") or 0)
    if profit < 0:
        r.hset("risk:state", values={"consecutive_losses": str(current + 1)})
    else:
        r.hset("risk:state", values={"consecutive_losses": "0"})

def reset_daily_if_needed(today_str: str, current_balance: float) -> bool:
    """Returns True if a reset was performed."""
    r = _r()
    last = r.hget("risk:state", "last_reset_date") or ""
    if last == today_str:
        return False
    r.hset("risk:state", values={
        "daily_start_balance": str(current_balance),
        "daily_loss_pct":      "0.0",
        "last_reset_date":     today_str,
    })
    return True


# ── Account snapshot ──────────────────────────────────────────
# Updated manually via /setstatus or seeded at deploy time.

def get_account_snapshot() -> dict:
    raw = _r().hgetall("account:snapshot") or {}
    return {
        "balance":    float(raw.get("balance", 0)),
        "equity":     float(raw.get("equity", 0)),
        "margin":     float(raw.get("margin", 0)),
        "currency":   raw.get("currency", "USD"),
        "updated_at": raw.get("updated_at", ""),
    }

def set_account_snapshot(data: dict) -> None:
    str_data = {k: str(v) for k, v in data.items()}
    _r().hset("account:snapshot", values=str_data)


# ── Cron concurrency lock ─────────────────────────────────────

def acquire_cron_lock() -> bool:
    """Returns True if lock was acquired (no other cron running)."""
    result = _r().set("cron:lock", "1", nx=True, ex=58)
    return result is not None

def release_cron_lock() -> None:
    _r().delete("cron:lock")


# ── Cron invocation counter (for periodic summaries) ─────────

def increment_invocation() -> int:
    return _r().incr("cron:invocation_count")


# ── Symbol strategy mode ──────────────────────────────────────
# Allows user to force a specific entry type via /setmode command.
# Values: "auto" | "pullback" | "pullback_sell" | "breakout" | "range"

_VALID_MODES = {"auto", "pullback", "pullback_sell", "breakout", "range"}

def get_symbol_mode(symbol: str) -> str:
    val = _r().get(f"symbol:{symbol}:mode")
    return val if val in _VALID_MODES else "auto"

def set_symbol_mode(symbol: str, mode: str) -> bool:
    if mode not in _VALID_MODES:
        return False
    _r().set(f"symbol:{symbol}:mode", mode)
    return True


# ── Candle cache (generic — all timeframes) ───────────────────

def get_cached_candles(symbol: str, timeframe: str) -> str | None:
    return _r().get(f"market_data:{symbol}:{timeframe}")

def set_cached_candles(symbol: str, timeframe: str, df_json: str, ttl: int = 300) -> None:
    _r().set(f"market_data:{symbol}:{timeframe}", df_json, ex=ttl)

# Backward-compatible aliases
def get_cached_m5(symbol: str) -> str | None:
    return get_cached_candles(symbol, "M5")

def set_cached_m5(symbol: str, df_json: str) -> None:
    set_cached_candles(symbol, "M5", df_json, ttl=300)


# ── Signal history log ────────────────────────────────────────
# Redis sorted set "signals:log"  (score = unix timestamp)
# Each member is a JSON string matching the signal record schema.
# Max 500 entries — oldest trimmed automatically on each write.

_SIGNALS_KEY  = "signals:log"
_SIGNALS_MAX  = 500


def log_signal(record: dict) -> None:
    """Append a signal record to the sorted set. Trims to last 500."""
    r   = _r()
    ts  = float(record.get("ts", 0))
    raw = json.dumps(record, ensure_ascii=False)
    r.zadd(_SIGNALS_KEY, {raw: ts})
    # keep only the newest MAX entries
    r.zremrangebyrank(_SIGNALS_KEY, 0, -(  _SIGNALS_MAX + 1))


def get_signal_history(n: int = 100) -> list:
    """Return the last n signals, newest first."""
    r    = _r()
    raws = r.zrange(_SIGNALS_KEY, 0, -1, rev=True)
    out  = []
    for raw in (raws or [])[:n]:
        try:
            out.append(json.loads(raw) if isinstance(raw, str) else raw)
        except Exception:
            pass
    return out


def get_open_sim_signals() -> list:
    """Return signals that have a SL/TP set but no sim_outcome yet."""
    all_sigs = get_signal_history(n=_SIGNALS_MAX)
    return [
        s for s in all_sigs
        if s.get("signal") in ("BUY", "SELL")
        and s.get("sl") and s.get("tp")
        and s.get("sim_outcome") is None
    ]


def update_sim_outcome(signal_id: str, outcome: str, close_price: float) -> None:
    """Find a signal by id and update its sim_outcome in place."""
    r    = _r()
    raws = r.zrange(_SIGNALS_KEY, 0, -1, withscores=True)
    for raw, score in (raws or []):
        try:
            rec = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if rec.get("id") != signal_id:
            continue
        # calculate pnl_r
        entry = rec.get("entry_price", 0)
        sl    = rec.get("sl", 0)
        tp    = rec.get("tp", 0)
        sl_dist = abs(entry - sl) if entry and sl else 0
        tp_dist = abs(tp - entry) if tp and entry else 0
        pnl_r = round(tp_dist / sl_dist, 2) if (outcome == "TP" and sl_dist) \
                else (-1.0 if outcome == "SL" else 0.0)

        rec["sim_outcome"]     = outcome
        rec["sim_close_price"] = close_price
        rec["sim_pnl_r"]       = pnl_r

        new_raw = json.dumps(rec, ensure_ascii=False)
        pipe = r.pipeline()
        pipe.zrem(_SIGNALS_KEY, raw)
        pipe.zadd(_SIGNALS_KEY, {new_raw: score})
        pipe.execute()
        return
