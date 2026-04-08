# ============================================================
#  lib/data_fetcher.py  —  Market data via Twelve Data API
#  Replaces MT5 data_fetcher.py (no MetaTrader5 dependency)
# ============================================================
import os
import requests
import pandas as pd

from lib.config import SYMBOL_MAP, SYMBOLS
import lib.state_store as store

TWELVE_BASE = "https://api.twelvedata.com"


def _api_key() -> str:
    key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY ยังไม่ได้ตั้งค่าใน Vercel env vars")
    return key


def _tf_to_interval(timeframe: str) -> str:
    """Convert "M1" / "M5" → Twelve Data interval string."""
    return {"M1": "1min", "M5": "5min"}.get(timeframe, "1min")


def get_candles(symbol: str, timeframe: str, count: int = 500) -> pd.DataFrame | None:
    """
    Fetch OHLCV candles from Twelve Data.
    symbol    : MT5-style name e.g. "XAUUSDm"
    timeframe : "M1" or "M5"
    Returns DataFrame with columns: open, high, low, close, volume
    Index: pd.DatetimeIndex (UTC)
    """
    # M5 — use Redis cache (5-min TTL) to stay within Twelve Data rate limits
    if timeframe == "M5":
        cached = store.get_cached_m5(symbol)
        if cached:
            try:
                df = pd.read_json(cached, orient="split")
                df.index = pd.to_datetime(df.index, utc=True)
                return df
            except Exception:
                pass  # cache corrupt → fetch fresh

    sym_cfg  = SYMBOL_MAP[symbol]
    td_sym   = sym_cfg["twelve_symbol"]
    interval = _tf_to_interval(timeframe)

    params = {
        "symbol":     td_sym,
        "interval":   interval,
        "outputsize": min(count, 5000),
        "apikey":     _api_key(),
        "timezone":   "UTC",
        "order":      "ASC",
    }
    # ระบุ exchange สำหรับ symbol ที่มีหลาย exchange (เช่น BTC/USD)
    if "twelve_exchange" in sym_cfg:
        params["exchange"] = sym_cfg["twelve_exchange"]

    try:
        resp = requests.get(f"{TWELVE_BASE}/time_series", params=params, timeout=15)
        data = resp.json()
    except Exception as e:
        print(f"[Data] ❌ HTTP error for {symbol} {timeframe}: {e}")
        return None

    if data.get("status") == "error" or "values" not in data:
        print(f"[Data] ❌ API error for {symbol} {timeframe}: {data.get('message', data)}")
        return None

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df.set_index("datetime", inplace=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # volume ไม่มีใน Forex/Gold — ใส่ 0 แทน
    if "volume" not in df.columns:
        df["volume"] = 0
    else:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df[["open", "high", "low", "close", "volume"]]

    if timeframe == "M5":
        store.set_cached_m5(symbol, df.to_json(orient="split", date_format="iso"))

    return df


def get_latest_price(symbol: str) -> tuple[float, float]:
    """
    Returns (ask, bid) estimated from Twelve Data /price.
    Twelve Data does not expose spread — estimate from config max_spread.
    """
    sym_cfg = SYMBOL_MAP[symbol]
    td_sym  = sym_cfg["twelve_symbol"]

    params = {"symbol": td_sym, "apikey": _api_key()}
    if "twelve_exchange" in sym_cfg:
        params["exchange"] = sym_cfg["twelve_exchange"]

    try:
        resp  = requests.get(f"{TWELVE_BASE}/price", params=params, timeout=8)
        price = float(resp.json().get("price", 0))
    except Exception as e:
        print(f"[Data] ❌ Price error for {symbol}: {e}")
        return 0.0, 0.0

    half   = SYMBOLS[symbol]["max_spread"] * sym_cfg["point_value"] * 0.3
    digits = sym_cfg["digits"]
    return round(price + half, digits), round(price - half, digits)


def get_latest_atr(symbol: str, timeframe: str = "M1", period: int = 14) -> float:
    df = get_candles(symbol, timeframe, count=period + 50)
    if df is None:
        return 1.0
    h, l, c = df["high"], df["low"], df["close"]
    tr  = pd.concat(
        [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return round(float(atr.iloc[-1]), 4)
