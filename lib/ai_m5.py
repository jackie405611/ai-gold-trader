# ============================================================
#  lib/ai_m5.py  —  M5 Trend Engine (V3)
# ============================================================
from lib.config import CONFIRM_BARS
from lib.indicators import ema, adx as calc_adx


def trend_signal(df):
    """
    ส่งคืน: "BUY" | "SELL" | "NONE"
    เงื่อนไข BUY  : EMA20 > EMA50 (ยืนยัน CONFIRM_BARS แท่ง) + ADX > 20 + +DI > -DI
    เงื่อนไข SELL : EMA20 < EMA50 (ยืนยัน CONFIRM_BARS แท่ง) + ADX > 20 + -DI > +DI
    """
    close = df["close"]
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)

    adx_s, plus_di, minus_di = calc_adx(df)

    last_adx     = adx_s.iloc[-1]
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
    adx_s, _, _ = calc_adx(df)
    return round(adx_s.iloc[-1], 2)
