# ============================================================
#  lib/indicators.py  —  Shared Technical Indicator Functions
#  ใช้ร่วมกันโดย ai_m5, ai_m1, ai_macd_rsi, ai_strategy
# ============================================================
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, p: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(com=p-1, adjust=False).mean()
    l = (-d).clip(lower=0).ewm(com=p-1, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, 1e-10))


def atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    h, lo, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h-lo, (h-c.shift()).abs(), (lo-c.shift()).abs()], axis=1).max(axis=1)
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

    # save raw values before mutual filter to avoid reading mutated series
    raw_plus  = high.diff().clip(lower=0)
    raw_minus = (-low.diff()).clip(lower=0)
    plus_dm   = raw_plus.where(raw_plus > raw_minus, 0)
    minus_dm  = raw_minus.where(raw_minus >= raw_plus, 0)

    tr       = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr_s    = tr.ewm(span=period, adjust=False).mean().replace(0, 1e-10)
    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr_s

    denom   = (plus_di + minus_di).replace(0, 1e-10)
    dx      = (100 * (plus_di - minus_di).abs() / denom).fillna(0)
    adx_val = dx.ewm(span=period, adjust=False).mean()

    return adx_val, plus_di, minus_di
