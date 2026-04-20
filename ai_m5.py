# ============================================================
#  ai_m5.py  —  M5 Trend Engine (V3)
# ============================================================
import pandas as pd
from config import CONFIRM_BARS


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _adx(df, period=14):
    """Average Directional Index — วัดความแรงของ trend"""
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    # save raw values before mutual filter to avoid reading mutated series
    raw_plus  = high.diff().clip(lower=0)
    raw_minus = (-low.diff()).clip(lower=0)
    plus_dm   = raw_plus.where(raw_plus > raw_minus, 0)
    minus_dm  = raw_minus.where(raw_minus >= raw_plus, 0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr      = tr.ewm(span=period, adjust=False).mean().replace(0, 1e-10)
    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr

    denom = (plus_di + minus_di).replace(0, 1e-10)
    dx    = (100 * (plus_di - minus_di).abs() / denom).fillna(0)
    adx   = dx.ewm(span=period, adjust=False).mean()

    return adx, plus_di, minus_di


def trend_signal(df):
    """
    ส่งคืน: "BUY" | "SELL" | "NONE"
    เงื่อนไข BUY  : EMA20 > EMA50 (ยืนยัน CONFIRM_BARS แท่ง) + ADX > 20 + +DI > -DI
    เงื่อนไข SELL : EMA20 < EMA50 (ยืนยัน CONFIRM_BARS แท่ง) + ADX > 20 + -DI > +DI
    """
    close = df["close"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)

    adx, plus_di, minus_di = _adx(df)

    last_adx     = adx.iloc[-1]
    trend_strong = last_adx > 20

    bullish_bars = sum(
        ema20.iloc[-i] > ema50.iloc[-i]
        for i in range(1, CONFIRM_BARS + 1)
    )
    bearish_bars = sum(
        ema20.iloc[-i] < ema50.iloc[-i]
        for i in range(1, CONFIRM_BARS + 1)
    )

    if bullish_bars == CONFIRM_BARS and trend_strong and plus_di.iloc[-1] > minus_di.iloc[-1]:
        return "BUY"

    if bearish_bars == CONFIRM_BARS and trend_strong and minus_di.iloc[-1] > plus_di.iloc[-1]:
        return "SELL"

    return "NONE"


def get_trend_strength(df):
    """คืน ADX value เพื่อแสดงในรายงาน"""
    adx, _, _ = _adx(df)
    return round(adx.iloc[-1], 2)
