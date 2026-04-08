# ============================================================
#  ai_m5.py  —  M5 Trend Engine  (V3)
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

    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    # ถ้า +DM < -DM ให้เป็น 0
    plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    adx = dx.ewm(span=period, adjust=False).mean()

    return adx, plus_di, minus_di


def trend_signal(df):
    """
    ส่งคืน: "BUY" | "SELL" | "NONE"
    เงื่อนไข BUY  : EMA20 > EMA50 (ยืนยัน CONFIRM_BARS แท่ง) + ADX > 20
    เงื่อนไข SELL : EMA20 < EMA50 (ยืนยัน CONFIRM_BARS แท่ง) + ADX > 20
    """
    close = df["close"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)

    adx, plus_di, minus_di = _adx(df)

    # ── ต้องยืนยัน N แท่งติดต่อกัน ──
    last_adx = adx.iloc[-1]

    bullish_bars = sum(
        ema20.iloc[-i] > ema50.iloc[-i]
        for i in range(1, CONFIRM_BARS + 1)
    )
    bearish_bars = sum(
        ema20.iloc[-i] < ema50.iloc[-i]
        for i in range(1, CONFIRM_BARS + 1)
    )

    trend_strong = last_adx > 20  # ADX > 20 = trend มีแรง

    if bullish_bars == CONFIRM_BARS and trend_strong and plus_di.iloc[-1] > minus_di.iloc[-1]:
        return "BUY"

    if bearish_bars == CONFIRM_BARS and trend_strong and minus_di.iloc[-1] > plus_di.iloc[-1]:
        return "SELL"

    return "NONE"


def get_trend_strength(df):
    """คืน ADX value เพื่อแสดงในรายงาน"""
    adx, _, _ = _adx(df)
    return round(adx.iloc[-1], 2)
