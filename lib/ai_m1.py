# ============================================================
#  lib/ai_m1.py  —  M1 Entry Engine (V3)
#  RSI_OVERSOLD / RSI_OVERBOUGHT รับจาก cfg ของแต่ละ symbol
# ============================================================
try:
    from lib.indicators import rsi as calc_rsi, ema as calc_ema, atr as calc_atr
except ImportError:
    from indicators import rsi as calc_rsi, ema as calc_ema, atr as calc_atr


def _is_bullish_candle(df, idx=-1):
    return df["close"].iloc[idx] > df["open"].iloc[idx]


def _is_bearish_candle(df, idx=-1):
    return df["close"].iloc[idx] < df["open"].iloc[idx]


def entry_signal(df, m5_trend="NONE", cfg=None):
    """
    ส่งคืน: ("BUY" | "SELL" | "NONE", rsi_value, atr_value)
    cfg : dict ของ symbol (จาก config.SYMBOLS) ใช้อ่าน rsi_oversold/rsi_overbought
    """
    oversold   = (cfg or {}).get("rsi_oversold",  38)
    overbought = (cfg or {}).get("rsi_overbought", 62)

    close = df["close"]
    rsi_s  = calc_rsi(close)
    ema20  = calc_ema(close, 20)
    atr_v  = calc_atr(df).iloc[-1]

    last_rsi   = rsi_s.iloc[-1]
    last_close = close.iloc[-1]
    last_ema20 = ema20.iloc[-1]

    signal = "NONE"

    if m5_trend == "BUY":
        if (last_rsi < oversold
                and last_close > last_ema20
                and _is_bullish_candle(df)):
            signal = "BUY"

    elif m5_trend == "SELL":
        if (last_rsi > overbought
                and last_close < last_ema20
                and _is_bearish_candle(df)):
            signal = "SELL"

    else:
        # ไม่มี M5 context → ใช้ signal อิสระ (conservative)
        if last_rsi < oversold - 5:
            signal = "BUY"
        elif last_rsi > overbought + 5:
            signal = "SELL"

    return signal, round(last_rsi, 2), round(atr_v, 4)
