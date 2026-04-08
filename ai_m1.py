# ============================================================
#  ai_m1.py  —  M1 Entry Engine  (V3)
#  RSI_OVERSOLD / RSI_OVERBOUGHT รับจาก cfg ของแต่ละ symbol
# ============================================================
import pandas as pd


def _rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _is_bullish_candle(df, idx=-1):
    """Candle ปิดสูงกว่าเปิด (bullish body)"""
    return df["close"].iloc[idx] > df["open"].iloc[idx]


def _is_bearish_candle(df, idx=-1):
    """Candle ปิดต่ำกว่าเปิด (bearish body)"""
    return df["close"].iloc[idx] < df["open"].iloc[idx]


def entry_signal(df, m5_trend="NONE", cfg=None):
    """
    ส่งคืน: ("BUY" | "SELL" | "NONE", rsi_value, atr_value)
    cfg : dict ของ symbol (จาก config.SYMBOLS) ใช้อ่าน rsi_oversold/rsi_overbought
    """
    oversold   = (cfg or {}).get("rsi_oversold",  38)
    overbought = (cfg or {}).get("rsi_overbought", 62)
    close  = df["close"]
    rsi    = _rsi(close)
    ema20  = _ema(close, 20)

    last_rsi   = rsi.iloc[-1]
    last_close = close.iloc[-1]
    last_ema20 = ema20.iloc[-1]

    # ATR สำหรับ SL/TP
    high  = df["high"]
    low   = df["low"]
    tr    = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr   = tr.ewm(span=14, adjust=False).mean().iloc[-1]

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

    return signal, round(last_rsi, 2), round(atr, 4)
