# ============================================================
#  lib/data_fetcher.py  —  Market data via Twelve Data API
#  Supports: M1, M5, M15, H1, H4
#  H4/H1/M15 are cached in Redis to avoid API rate limits.
# ============================================================
import os
import requests
import pandas as pd

from lib.config import SYMBOL_MAP, SYMBOLS
import lib.state_store as store

TWELVE_BASE = "https://api.twelvedata.com"

# Cache TTL per timeframe (seconds) — longer TF = longer cache
_CACHE_TTL = {
    "M1":  0,     # no cache
    "M5":  300,   # 5 min
    "M15": 900,   # 15 min
    "H1":  3600,  # 1 hour
    "H4":  14400, # 4 hours
}

_TF_INTERVAL = {
    "M1":  "1min",
    "M5":  "5min",
    "M15": "15min",
    "H1":  "1h",
    "H4":  "4h",
}


def _api_key() -> str:
    key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY ยังไม่ได้ตั้งค่าใน Vercel env vars")
    return key


def get_candles(symbol: str, timeframe: str, count: int = 100) -> pd.DataFrame | None:
    """
    Fetch OHLCV candles from Twelve Data.
    symbol    : MT5-style name e.g. "XAUUSDm"
    timeframe : "M1" | "M5" | "M15" | "H1" | "H4"
    Returns DataFrame with columns: open, high, low, close, volume
    """
    # Use Redis cache for slower timeframes
    ttl = _CACHE_TTL.get(timeframe, 0)
    if ttl > 0:
        cached = store.get_cached_candles(symbol, timeframe)
        if cached:
            try:
                df = pd.read_json(cached, orient="split")
                df.index = pd.to_datetime(df.index, utc=True)
                return df
            except Exception:
                pass

    sym_cfg  = SYMBOL_MAP[symbol]
    td_sym   = sym_cfg["twelve_symbol"]
    interval = _TF_INTERVAL.get(timeframe, "1min")

    params = {
        "symbol":     td_sym,
        "interval":   interval,
        "outputsize": min(count, 5000),
        "apikey":     _api_key(),
        "timezone":   "UTC",
        "order":      "ASC",
    }
    if "twelve_exchange" in sym_cfg:
        params["exchange"] = sym_cfg["twelve_exchange"]

    try:
        resp = requests.get(f"{TWELVE_BASE}/time_series", params=params, timeout=15)
        data = resp.json()
    except Exception as e:
        print(f"[Data] ❌ HTTP error {symbol} {timeframe}: {e}")
        return None

    if data.get("status") == "error" or "values" not in data:
        print(f"[Data] ❌ API error {symbol} {timeframe}: {data.get('message', data)}")
        return None

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df.set_index("datetime", inplace=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 0
    else:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df[["open", "high", "low", "close", "volume"]]

    if ttl > 0:
        store.set_cached_candles(symbol, timeframe,
                                 df.to_json(orient="split", date_format="iso"), ttl=ttl)

    return df


def get_latest_price(symbol: str) -> tuple:
    """
    Returns (ask, bid) estimated from Twelve Data /price.
    Spread is estimated from config max_spread.
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
        print(f"[Data] ❌ Price error {symbol}: {e}")
        return 0.0, 0.0

    half   = SYMBOLS[symbol]["max_spread"] * sym_cfg["point_value"] * 0.3
    digits = sym_cfg["digits"]
    return round(price + half, digits), round(price - half, digits)


def get_latest_atr(symbol: str, timeframe: str = "M15", period: int = 14) -> float:
    df = get_candles(symbol, timeframe, count=period + 50)
    if df is None:
        return 1.0
    h, l, c = df["high"], df["low"], df["close"]
    tr  = pd.concat(
        [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return round(float(atr.iloc[-1]), 4)
