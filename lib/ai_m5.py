# ============================================================
#  lib/ai_m5.py  —  H4 Trend Structure (legacy shim)
#  Logic moved to ai_strategy._h4_structure().
#  This module is kept for backward compatibility only.
# ============================================================
try:
    from lib.indicators import ema, market_structure
except ImportError:
    from indicators import ema, market_structure


def trend_signal(df_h4) -> str:
    """
    Returns "BUY" | "SELL" | "NONE"
    Wrapper around H4 structure — used by legacy code paths.
    """
    close  = df_h4["close"]
    ema50  = ema(close, 50)
    ema200 = ema(close, 200)
    last_c  = float(close.iloc[-1])
    last_e50  = float(ema50.iloc[-1])
    last_e200 = float(ema200.iloc[-1])

    structure = market_structure(df_h4, lookback=40)

    if structure == "UPTREND" and last_c > last_e50:
        return "BUY"
    elif structure == "DOWNTREND" and last_c < last_e50:
        return "SELL"
    return "NONE"


def get_trend_strength(df_h4) -> str:
    return market_structure(df_h4, lookback=40)
