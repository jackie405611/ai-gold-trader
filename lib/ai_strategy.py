# ============================================================
#  lib/ai_strategy.py  —  Signal Aggregator + Market Regime (V3)
#
#  Regime-based routing:
#    TRENDING  → Strategy 1: EMA20/50 + ADX (via ai_m5) + M1 pullback entry
#    RANGING   → Strategy 2: MACD crossover + RSI extremes (via ai_macd_rsi)
#    VOLATILE  → NO TRADE
# ============================================================
from lib.ai_macd_rsi import macd_rsi_signal
from lib.ai_m5 import trend_signal
from lib.ai_m1 import entry_signal
from lib.indicators import atr as calc_atr, bollinger_width, adx as calc_adx


# ── Market Regime Detection ───────────────────────────────────

def detect_regime(df, max_volatility=8.0):
    """คืน: "TRENDING" | "RANGING" | "VOLATILE", adx_val, atr_val"""
    atr_val  = calc_atr(df).iloc[-1]
    adx_s, _, _ = calc_adx(df)
    adx_val  = adx_s.iloc[-1]

    if atr_val > max_volatility:
        return "VOLATILE", adx_val, atr_val
    elif adx_val > 25:
        return "TRENDING", adx_val, atr_val
    else:
        return "RANGING", adx_val, atr_val


# ── Strategy 1: Trend ─────────────────────────────────────────

def _trend_strategy(df_m5, df_m1, cfg):
    """
    ใช้ trend_signal (EMA20/50 + ADX + CONFIRM_BARS) จาก ai_m5
    + entry_signal (RSI pullback + candle body) จาก ai_m1 เป็น M1 confirmation
    """
    m5_sig = trend_signal(df_m5)
    info   = {"strategy": "TREND", "m5_signal": m5_sig}

    if m5_sig == "NONE":
        return "NO TRADE", {**info, "reason": "No M5 EMA/ADX trend"}

    if df_m1 is not None:
        m1_sig, m1_rsi, _ = entry_signal(df_m1, m5_trend=m5_sig, cfg=cfg)
        info["m1_rsi"] = m1_rsi
        if m1_sig == "NONE":
            return "NO TRADE", {**info, "reason": f"M1 entry not confirmed (RSI {m1_rsi})"}

    return m5_sig, {**info, "reason": "EMA trend + ADX + M1 pullback confirmed"}


# ── Main Signal Generator ─────────────────────────────────────

def generate_signal(df_m5, df_m1=None, cfg=None):
    """
    Input : df_m5, df_m1 (optional), cfg (dict ของ symbol จาก config.SYMBOLS)
    Output: "BUY" | "SELL" | "NO TRADE", dict(info)

    TRENDING → Trend strategy  (EMA crossover + ADX)
    RANGING  → Reversal strategy (MACD + RSI extremes)
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

    # ── Route by regime ──
    if regime == "TRENDING":
        sig, info = _trend_strategy(df_m5, df_m1, cfg)
    else:  # RANGING
        sig, info = macd_rsi_signal(df_m5, df_m1, cfg)

    return sig, {**base_info, **info}
