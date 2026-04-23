# ============================================================
#  lib/ai_m1.py  —  M15 Entry Confirmation (legacy shim)
#  Logic moved to ai_strategy._m15_confirmation().
#  This module is kept for backward compatibility only.
# ============================================================
try:
    from lib.indicators import (
        rsi as calc_rsi, atr as calc_atr,
        is_pin_bar_bullish, is_pin_bar_bearish,
        is_bullish_engulfing, is_bearish_engulfing,
        break_of_structure_bullish, break_of_structure_bearish,
    )
except ImportError:
    from indicators import (
        rsi as calc_rsi, atr as calc_atr,
        is_pin_bar_bullish, is_pin_bar_bearish,
        is_bullish_engulfing, is_bearish_engulfing,
        break_of_structure_bullish, break_of_structure_bearish,
    )


def entry_signal(df_m15, m5_trend="NONE", cfg=None):
    """
    Returns ("BUY" | "SELL" | "NONE", rsi_value, atr_value)
    Checks price action patterns on M15 for entry confirmation.
    """
    close   = df_m15["close"]
    rsi_val = float(calc_rsi(close).iloc[-1])
    atr_val = float(calc_atr(df_m15).iloc[-1])

    signal = "NONE"

    if m5_trend == "BUY":
        if is_pin_bar_bullish(df_m15) or is_bullish_engulfing(df_m15):
            signal = "BUY"
        elif break_of_structure_bullish(df_m15):
            signal = "BUY"

    elif m5_trend == "SELL":
        if is_pin_bar_bearish(df_m15) or is_bearish_engulfing(df_m15):
            signal = "SELL"
        elif break_of_structure_bearish(df_m15):
            signal = "SELL"

    return signal, round(rsi_val, 2), round(atr_val, 4)
