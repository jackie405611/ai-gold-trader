# ============================================================
#  lib/indicators.py  —  Technical Indicator Functions
#  ใช้ร่วมกันโดย ai_strategy และ modules ทั้งหมด
# ============================================================
import pandas as pd


# ── Basic Indicators ──────────────────────────────────────────

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, p: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(com=p - 1, adjust=False).mean()
    l = (-d).clip(lower=0).ewm(com=p - 1, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, 1e-10))


def atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    h, lo, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()


def bollinger_width(s: pd.Series, p: int = 20) -> float:
    std = s.rolling(p).std()
    mid = s.rolling(p).mean()
    val = (2 * std / mid.replace(0, 1e-10) * 100).iloc[-1]
    return float(val) if pd.notna(val) else 0.0


def adx(df: pd.DataFrame, period: int = 14):
    """Returns (adx_series, plus_di_series, minus_di_series)"""
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    raw_plus  = high.diff().clip(lower=0)
    raw_minus = (-low.diff()).clip(lower=0)
    plus_dm   = raw_plus.where(raw_plus > raw_minus, 0)
    minus_dm  = raw_minus.where(raw_minus >= raw_plus, 0)

    tr       = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_s    = tr.ewm(span=period, adjust=False).mean().replace(0, 1e-10)
    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr_s

    denom   = (plus_di + minus_di).replace(0, 1e-10)
    dx      = (100 * (plus_di - minus_di).abs() / denom).fillna(0)
    adx_val = dx.ewm(span=period, adjust=False).mean()

    return adx_val, plus_di, minus_di


# ── Swing Points ──────────────────────────────────────────────

def swing_highs(df: pd.DataFrame, left: int = 5, right: int = 3) -> pd.Series:
    """Boolean Series — True at swing high bars."""
    high   = df["high"].reset_index(drop=True)
    result = pd.Series(False, index=range(len(df)))
    for i in range(left, len(df) - right):
        window = high.iloc[i - left: i + right + 1]
        if high.iloc[i] == window.max():
            result.iloc[i] = True
    result.index = df.index
    return result


def swing_lows(df: pd.DataFrame, left: int = 5, right: int = 3) -> pd.Series:
    """Boolean Series — True at swing low bars."""
    low    = df["low"].reset_index(drop=True)
    result = pd.Series(False, index=range(len(df)))
    for i in range(left, len(df) - right):
        window = low.iloc[i - left: i + right + 1]
        if low.iloc[i] == window.min():
            result.iloc[i] = True
    result.index = df.index
    return result


def market_structure(df: pd.DataFrame, lookback: int = 40) -> str:
    """
    Returns "UPTREND" | "DOWNTREND" | "SIDEWAYS"
    Based on Higher High / Higher Low  or  Lower High / Lower Low pattern.
    """
    sub = df.tail(lookback).copy()
    sh  = swing_highs(sub, left=3, right=3)
    sl  = swing_lows(sub, left=3, right=3)

    swing_h_prices = sub["high"][sh].values
    swing_l_prices = sub["low"][sl].values

    if len(swing_h_prices) < 2 or len(swing_l_prices) < 2:
        return "SIDEWAYS"

    hh = swing_h_prices[-1] > swing_h_prices[-2]
    hl = swing_l_prices[-1] > swing_l_prices[-2]
    lh = swing_h_prices[-1] < swing_h_prices[-2]
    ll = swing_l_prices[-1] < swing_l_prices[-2]

    if hh and hl:
        return "UPTREND"
    elif lh and ll:
        return "DOWNTREND"
    else:
        return "SIDEWAYS"


# ── Fibonacci Retracement ─────────────────────────────────────

def fibonacci_levels(swing_low: float, swing_high: float) -> dict:
    """Key Fibonacci retracement levels from swing low to swing high."""
    diff = swing_high - swing_low
    return {
        "0.236": round(swing_high - 0.236 * diff, 4),
        "0.382": round(swing_high - 0.382 * diff, 4),
        "0.500": round(swing_high - 0.500 * diff, 4),
        "0.618": round(swing_high - 0.618 * diff, 4),
        "0.786": round(swing_high - 0.786 * diff, 4),
    }


def find_fib_zone(price: float, fib_levels: dict, tolerance_pct: float = 0.003) -> str | None:
    """Returns Fibonacci level name if price is within tolerance%, else None."""
    for name, level in fib_levels.items():
        if level > 0 and abs(price - level) / level <= tolerance_pct:
            return name
    return None


# ── Support / Resistance Zones ────────────────────────────────

def find_support_zones(df: pd.DataFrame, n: int = 5, lookback: int = 60) -> list:
    """Recent support levels from swing lows."""
    sub    = df.tail(lookback).copy()
    sl_mask = swing_lows(sub, left=3, right=2)
    levels = sorted(sub["low"][sl_mask].values)
    return [round(float(v), 4) for v in levels[-n:]]


def find_resistance_zones(df: pd.DataFrame, n: int = 5, lookback: int = 60) -> list:
    """Recent resistance levels from swing highs."""
    sub    = df.tail(lookback).copy()
    sh_mask = swing_highs(sub, left=3, right=2)
    levels = sorted(sub["high"][sh_mask].values)
    return [round(float(v), 4) for v in levels[-n:]]


def price_near_zone(price: float, zones: list, tolerance_pct: float = 0.003) -> bool:
    """True if price is within tolerance% of any zone."""
    for z in zones:
        if z > 0 and abs(price - z) / z <= tolerance_pct:
            return True
    return False


def nearest_resistance_above(price: float, zones: list) -> float | None:
    """Nearest resistance level strictly above current price."""
    above = [z for z in zones if z > price]
    return min(above) if above else None


def nearest_support_below(price: float, zones: list) -> float | None:
    """Nearest support level strictly below current price."""
    below = [z for z in zones if z < price]
    return max(below) if below else None


# ── Price Action Patterns ─────────────────────────────────────

def is_pin_bar_bullish(df: pd.DataFrame, idx: int = -1, min_tail_ratio: float = 2.0) -> bool:
    """
    Bullish pin bar (hammer): long lower wick >= min_tail_ratio × body,
    lower wick > upper wick.
    """
    o = float(df["open"].iloc[idx])
    h = float(df["high"].iloc[idx])
    l = float(df["low"].iloc[idx])
    c = float(df["close"].iloc[idx])

    body       = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    if body < 1e-10:
        return False
    return lower_wick >= min_tail_ratio * body and lower_wick > upper_wick


def is_pin_bar_bearish(df: pd.DataFrame, idx: int = -1, min_tail_ratio: float = 2.0) -> bool:
    """
    Bearish pin bar (shooting star): long upper wick >= min_tail_ratio × body,
    upper wick > lower wick.
    """
    o = float(df["open"].iloc[idx])
    h = float(df["high"].iloc[idx])
    l = float(df["low"].iloc[idx])
    c = float(df["close"].iloc[idx])

    body       = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body < 1e-10:
        return False
    return upper_wick >= min_tail_ratio * body and upper_wick > lower_wick


def is_bullish_engulfing(df: pd.DataFrame, idx: int = -1) -> bool:
    """Current bullish body fully engulfs previous bearish body."""
    if len(df) < 2:
        return False
    prev = idx - 1
    o1, c1 = float(df["open"].iloc[prev]), float(df["close"].iloc[prev])
    o2, c2 = float(df["open"].iloc[idx]),  float(df["close"].iloc[idx])

    prev_bearish = c1 < o1
    curr_bullish = c2 > o2
    engulfs      = c2 > o1 and o2 < c1

    return prev_bearish and curr_bullish and engulfs


def is_bearish_engulfing(df: pd.DataFrame, idx: int = -1) -> bool:
    """Current bearish body fully engulfs previous bullish body."""
    if len(df) < 2:
        return False
    prev = idx - 1
    o1, c1 = float(df["open"].iloc[prev]), float(df["close"].iloc[prev])
    o2, c2 = float(df["open"].iloc[idx]),  float(df["close"].iloc[idx])

    prev_bullish = c1 > o1
    curr_bearish = c2 < o2
    engulfs      = c2 < o1 and o2 > c1

    return prev_bullish and curr_bearish and engulfs


def is_morning_star(df: pd.DataFrame) -> bool:
    """
    3-candle bullish reversal:
    Candle 1 = bearish  |  Candle 2 = small body  |  Candle 3 = bullish above midpoint of C1.
    """
    if len(df) < 3:
        return False
    o1, c1 = float(df["open"].iloc[-3]), float(df["close"].iloc[-3])
    o2, c2 = float(df["open"].iloc[-2]), float(df["close"].iloc[-2])
    o3, c3 = float(df["open"].iloc[-1]), float(df["close"].iloc[-1])

    c1_bearish  = c1 < o1
    c1_body     = abs(c1 - o1)
    c2_small    = abs(c2 - o2) < c1_body * 0.35
    c3_bullish  = c3 > o3
    c3_above_mid = c3 > (o1 + c1) / 2

    return c1_bearish and c2_small and c3_bullish and c3_above_mid


# ── Break of Structure ────────────────────────────────────────

def break_of_structure_bullish(df: pd.DataFrame, lookback: int = 20) -> bool:
    """
    BOS Bullish: latest close breaks above the most recent confirmed swing high
    within the lookback window (signals downtrend is ending / uptrend starting).
    """
    if len(df) < lookback + 5:
        return False
    sub     = df.iloc[-(lookback + 5): -1].copy()  # exclude very last bar
    sh_mask = swing_highs(sub, left=3, right=2)
    sh_prices = sub["high"][sh_mask].values
    if len(sh_prices) < 1:
        return False
    last_sh = sh_prices[-1]
    return float(df["close"].iloc[-1]) > last_sh


def break_of_structure_bearish(df: pd.DataFrame, lookback: int = 20) -> bool:
    """
    BOS Bearish: latest close breaks below the most recent confirmed swing low.
    """
    if len(df) < lookback + 5:
        return False
    sub     = df.iloc[-(lookback + 5): -1].copy()
    sl_mask = swing_lows(sub, left=3, right=2)
    sl_prices = sub["low"][sl_mask].values
    if len(sl_prices) < 1:
        return False
    last_sl = sl_prices[-1]
    return float(df["close"].iloc[-1]) < last_sl
