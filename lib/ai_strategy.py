# ============================================================
#  lib/ai_strategy.py  —  Signal Aggregator + Market Regime (V3)
#  Fixes:
#   - ADX DM filter now uses original series (not mutated)
#   - M1 RSI threshold reads from cfg (62/38) not hardcoded 70/30
#   - Bollinger width guards against NaN
# ============================================================
import pandas as pd


# ── Helpers ──────────────────────────────────────────────────

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def _rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(com=p-1, adjust=False).mean()
    l = (-d).clip(lower=0).ewm(com=p-1, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, 1e-10))

def _atr(df, p=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def _bollinger_width(s, p=20):
    std = s.rolling(p).std()
    mid = s.rolling(p).mean()
    val = (2 * std / mid.replace(0, 1e-10) * 100).iloc[-1]
    return float(val) if pd.notna(val) else 0.0


# ── Market Regime Detection ───────────────────────────────────

def detect_regime(df, max_volatility=8.0):
    """
    คืน: "TRENDING" | "RANGING" | "VOLATILE"
    max_volatility : อ่านจาก cfg ของแต่ละ symbol
    """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    atr_val  = _atr(df).iloc[-1]
    bb_width = _bollinger_width(close)

    # ── ADX (fix: save raw DM before mutual filter) ──
    raw_plus  = high.diff().clip(lower=0)
    raw_minus = (-low.diff()).clip(lower=0)
    plus_dm   = raw_plus.where(raw_plus > raw_minus, 0)
    minus_dm  = raw_minus.where(raw_minus >= raw_plus, 0)   # >= handles equal case

    tr     = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr_s  = tr.ewm(span=14, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(span=14, adjust=False).mean() / atr_s.replace(0, 1e-10)
    minus_di = 100 * minus_dm.ewm(span=14, adjust=False).mean() / atr_s.replace(0, 1e-10)
    dx       = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    adx      = dx.ewm(span=14, adjust=False).mean().iloc[-1]

    if atr_val > max_volatility:
        return "VOLATILE", adx, atr_val
    elif adx > 25:
        return "TRENDING", adx, atr_val
    else:
        return "RANGING", adx, atr_val


# ── Main Signal Generator ─────────────────────────────────────

def generate_signal(df_m5, df_m1=None, cfg=None):
    """
    Input : df_m5, df_m1 (optional), cfg (dict ของ symbol จาก config.SYMBOLS)
    Output: "BUY" | "SELL" | "NO TRADE", dict(info)
    """
    cfg      = cfg or {}
    min_vol  = cfg.get("min_volatility", 0.3)
    max_vol  = cfg.get("max_volatility",  8.0)
    # อ่าน threshold จาก cfg (ค่า default 62/38 ตรงกับ config.py)
    rsi_ob   = cfg.get("rsi_overbought", 62)
    rsi_os   = cfg.get("rsi_oversold",   38)

    # ── 1. Regime ──
    regime, adx_val, atr_val = detect_regime(df_m5, max_vol)
    info = {
        "regime": regime,
        "adx":    round(adx_val, 1),
        "atr":    round(atr_val, 4),
    }

    if regime == "VOLATILE":
        return "NO TRADE", {**info, "reason": "High volatility / news spike"}

    if atr_val < min_vol:
        return "NO TRADE", {**info, "reason": "Market too quiet (low ATR)"}

    # ── 2. M5 Signal ──
    close    = df_m5["close"]
    ema_f    = _ema(close, 20)
    ema_s    = _ema(close, 50)
    rsi_v    = _rsi(close)

    fast     = ema_f.iloc[-1]
    slow     = ema_s.iloc[-1]
    last_rsi = rsi_v.iloc[-1]

    m5_signal = "NONE"
    if fast > slow and last_rsi > 50:
        m5_signal = "BUY"
    elif fast < slow and last_rsi < 50:
        m5_signal = "SELL"

    info["m5_signal"] = m5_signal
    info["m5_rsi"]    = round(last_rsi, 1)

    if m5_signal == "NONE":
        return "NO TRADE", {**info, "reason": "No M5 consensus"}

    # ── 3. M1 Confirmation ──
    # กรอง: ไม่ BUY ตอน M1 overbought, ไม่ SELL ตอน M1 oversold
    # ใช้ threshold จาก cfg (62/38) ไม่ hardcode 70/30
    if df_m1 is not None:
        m1_close = df_m1["close"]
        m1_rsi   = _rsi(m1_close).iloc[-1]
        info["m1_rsi"] = round(m1_rsi, 1)

        if m5_signal == "BUY"  and m1_rsi > rsi_ob:
            return "NO TRADE", {**info, "reason": f"M1 overbought (RSI {m1_rsi:.0f} > {rsi_ob})"}
        if m5_signal == "SELL" and m1_rsi < rsi_os:
            return "NO TRADE", {**info, "reason": f"M1 oversold (RSI {m1_rsi:.0f} < {rsi_os})"}

    return m5_signal, {**info, "reason": "OK"}
