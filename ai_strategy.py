# ============================================================
#  ai_strategy.py  —  Signal Aggregator + Market Regime (V3)
#
#  Regime-based routing:
#    TRENDING  → Strategy 1: EMA20/50 + ADX (via ai_m5) + M1 pullback entry
#    RANGING   → Strategy 2: MACD crossover + RSI extremes (via lib.ai_macd_rsi)
#    VOLATILE  → NO TRADE
# ============================================================
import pandas as pd
from ai_m5 import trend_signal, _adx
from ai_m1 import entry_signal

try:
    from lib.ai_macd_rsi import macd_rsi_signal
    _HAS_REVERSAL = True
except ImportError:
    _HAS_REVERSAL = False


def _atr(df, p=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()


# ── Market Regime Detection ───────────────────────────────────

def detect_regime(df, max_volatility=8.0):
    """คืน: "TRENDING" | "RANGING" | "VOLATILE", adx_val, atr_val"""
    atr_val = _atr(df).iloc[-1]
    adx_s, _, _ = _adx(df)
    adx_val = adx_s.iloc[-1]

    if atr_val > max_volatility:
        return "VOLATILE", adx_val, atr_val
    elif adx_val > 25:
        return "TRENDING", adx_val, atr_val
    else:
        return "RANGING", adx_val, atr_val


# ── Strategy 1: Trend ─────────────────────────────────────────

def _trend_strategy(df_m5, df_m1, cfg):
    """EMA20/50 + ADX (via ai_m5) + M1 pullback confirmation (via ai_m1)"""
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
    RANGING  → Reversal strategy (MACD + RSI) ถ้ามี lib.ai_macd_rsi, ไม่งั้น Trend
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
    if regime == "RANGING" and _HAS_REVERSAL:
        sig, info = macd_rsi_signal(df_m5, df_m1, cfg)
    else:
        sig, info = _trend_strategy(df_m5, df_m1, cfg)

    return sig, {**base_info, **info}
