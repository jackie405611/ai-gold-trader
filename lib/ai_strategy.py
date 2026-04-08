# ============================================================
#  lib/ai_strategy.py  —  Signal Aggregator + Market Regime (V3)
#
#  Strategy 1 (Trend):    EMA20/50 + RSI M5 + M1 confirmation
#  Strategy 2 (Reversal): MACD crossover + RSI oversold/overbought
#
#  สัญญาณออกเมื่อ strategy ใดอย่างน้อยหนึ่งให้สัญญาณ
#  (ทั้งสองต้องผ่าน ATR / Volatility gate ก่อน)
# ============================================================
import pandas as pd
from lib.ai_macd_rsi import macd_rsi_signal


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
    """คืน: "TRENDING" | "RANGING" | "VOLATILE" """
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    atr_val  = _atr(df).iloc[-1]
    bb_width = _bollinger_width(close)

    # ADX (ใช้ raw series ก่อน mutual filter)
    raw_plus  = high.diff().clip(lower=0)
    raw_minus = (-low.diff()).clip(lower=0)
    plus_dm   = raw_plus.where(raw_plus > raw_minus, 0)
    minus_dm  = raw_minus.where(raw_minus >= raw_plus, 0)

    tr       = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr_s    = tr.ewm(span=14, adjust=False).mean().replace(0, 1e-10)
    plus_di  = 100 * plus_dm.ewm(span=14, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(span=14, adjust=False).mean() / atr_s
    dx       = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    adx      = dx.ewm(span=14, adjust=False).mean().iloc[-1]

    if atr_val > max_volatility:
        return "VOLATILE", adx, atr_val
    elif adx > 25:
        return "TRENDING", adx, atr_val
    else:
        return "RANGING", adx, atr_val


# ── Strategy 1: Trend (EMA + RSI) ────────────────────────────

def _trend_signal(df_m5, df_m1, cfg):
    """EMA20/50 crossover + RSI M5 + M1 confirmation"""
    rsi_ob = cfg.get("rsi_overbought", 62)
    rsi_os = cfg.get("rsi_oversold",   38)

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

    info = {
        "strategy":  "TREND",
        "m5_signal": m5_signal,
        "m5_rsi":    round(last_rsi, 1),
    }

    if m5_signal == "NONE":
        return "NO TRADE", {**info, "reason": "No M5 EMA/RSI consensus"}

    # M1 confirmation
    if df_m1 is not None:
        m1_rsi = _rsi(df_m1["close"]).iloc[-1]
        info["m1_rsi"] = round(m1_rsi, 1)
        if m5_signal == "BUY"  and m1_rsi > rsi_ob:
            return "NO TRADE", {**info, "reason": f"M1 overbought (RSI {m1_rsi:.0f} > {rsi_ob})"}
        if m5_signal == "SELL" and m1_rsi < rsi_os:
            return "NO TRADE", {**info, "reason": f"M1 oversold (RSI {m1_rsi:.0f} < {rsi_os})"}

    return m5_signal, {**info, "reason": "EMA trend confirmed"}


# ── Main Signal Generator ─────────────────────────────────────

def generate_signal(df_m5, df_m1=None, cfg=None):
    """
    รัน 2 strategies คู่กัน:
      1. Trend   : EMA20/50 + RSI
      2. Reversal: MACD crossover + RSI oversold/overbought + M1 timing

    Output: "BUY" | "SELL" | "NO TRADE", dict(info)
    """
    cfg     = cfg or {}
    min_vol = cfg.get("min_volatility", 0.3)
    max_vol = cfg.get("max_volatility",  8.0)

    # ── Gate: Volatility + Regime ──
    regime, adx_val, atr_val = detect_regime(df_m5, max_vol)
    base_info = {
        "regime": regime,
        "adx":    round(adx_val, 1),
        "atr":    round(atr_val, 4),
    }

    if regime == "VOLATILE":
        return "NO TRADE", {**base_info, "reason": "High volatility / news spike"}

    if atr_val < min_vol:
        return "NO TRADE", {**base_info, "reason": "Market too quiet (low ATR)"}

    # ── Strategy 1: Trend ──
    trend_sig, trend_info = _trend_signal(df_m5, df_m1, cfg)

    # ── Strategy 2: Reversal (MACD + RSI) ──
    reversal_sig, reversal_info = macd_rsi_signal(df_m5, df_m1, cfg)

    # ── รวมสัญญาณ ──
    # ถ้าทั้งสองตรงกัน → ส่งสัญญาณ (เชื่อถือได้มากขึ้น)
    # ถ้ามีแค่อันเดียว → ส่งสัญญาณ (พร้อมบอก source)
    # ถ้าขัดแย้งกัน   → NO TRADE
    signals = {s for s in [trend_sig, reversal_sig] if s in ("BUY", "SELL")}

    if len(signals) == 0:
        # ทั้งคู่ NO TRADE
        return "NO TRADE", {
            **base_info,
            "trend":    trend_info.get("reason", ""),
            "reversal": reversal_info.get("reason", ""),
            "reason":   "No signal from either strategy",
        }

    if len(signals) == 2 and "BUY" in signals and "SELL" in signals:
        # ขัดแย้งกัน
        return "NO TRADE", {
            **base_info,
            "trend":    trend_sig,
            "reversal": reversal_sig,
            "reason":   "Strategies conflict (BUY vs SELL)",
        }

    # มีสัญญาณ
    final_sig  = signals.pop()
    both_agree = (trend_sig == reversal_sig)
    source     = "BOTH strategies" if both_agree else (
        "TREND" if trend_sig == final_sig else "REVERSAL"
    )

    return final_sig, {
        **base_info,
        "m5_rsi":      trend_info.get("m5_rsi", reversal_info.get("m5_rsi")),
        "m1_rsi":      trend_info.get("m1_rsi", reversal_info.get("m1_rsi")),
        "macd":        reversal_info.get("macd"),
        "macd_cross":  reversal_info.get("macd_cross"),
        "m5_signal":   final_sig,
        "source":      source,
        "reason":      f"{source}: {reversal_info.get('reason', trend_info.get('reason', 'OK'))}",
    }
