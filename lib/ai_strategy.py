# ============================================================
#  lib/ai_strategy.py  —  6-Layer Intraday Gold Strategy
#
#  Pipeline (top-down, shift to shorter TFs for day trading):
#    Layer 1 (H4):  Broad bias — soft filter, counter-trend skipped
#    Layer 2 (H1):  Intraday trend (primary direction driver)
#    Layer 3 (M15): Zone finding — S/R + H1 Fibo + EMA confluence ≥ 2
#    Layer 4 (M5):  Setup confirmation — Price action + BOS
#    Layer 5 (M1):  Precise entry timing — micro PA
#    Layer 6:       SL (M5 swing) / TP (M15 level) / R:R ≥ 1.5
#
#  Entry types:
#    PULLBACK       — H1 uptrend + M15 pullback to support zone
#    PULLBACK_SELL  — H1 downtrend + M15 pullback to resistance
#    BREAKOUT_RETEST — H1 breaks level + retests from other side
#    RANGE_SUPPORT  — H1 sideways + price at M15 range support
# ============================================================
try:
    from lib.indicators import (
        ema, rsi, atr as calc_atr,
        market_structure, fibonacci_levels, find_fib_zone,
        find_support_zones, find_resistance_zones,
        price_near_zone, nearest_resistance_above, nearest_support_below,
        is_pin_bar_bullish, is_pin_bar_bearish,
        is_bullish_engulfing, is_bearish_engulfing,
        is_morning_star,
        break_of_structure_bullish, break_of_structure_bearish,
        swing_lows, swing_highs,
    )
except ImportError:
    from indicators import (
        ema, rsi, atr as calc_atr,
        market_structure, fibonacci_levels, find_fib_zone,
        find_support_zones, find_resistance_zones,
        price_near_zone, nearest_resistance_above, nearest_support_below,
        is_pin_bar_bullish, is_pin_bar_bearish,
        is_bullish_engulfing, is_bearish_engulfing,
        is_morning_star,
        break_of_structure_bullish, break_of_structure_bearish,
        swing_lows, swing_highs,
    )


# ── Layer 1: H4 Broad Bias (soft filter) ─────────────────────

def _h4_bias(df_h4) -> str:
    """Quick H4 bias check — counter-trend trades are skipped, not hard-blocked."""
    close = df_h4["close"]
    e50   = float(ema(close, 50).iloc[-1])
    e200  = float(ema(close, 200).iloc[-1])
    last  = float(close.iloc[-1])
    if last > e50 > e200:
        return "BULL"
    elif last < e50 < e200:
        return "BEAR"
    return "NEUTRAL"


# ── Layer 2: H1 Intraday Trend ────────────────────────────────

def _h1_trend(df_h1) -> tuple:
    """
    Returns (bias, info_dict)
    bias: "UPTREND" | "DOWNTREND" | "SIDEWAYS"
    Primary intraday direction driver — replaces H4 as trend engine.
    """
    close     = df_h1["close"]
    ema50     = ema(close, 50)
    ema200    = ema(close, 200)
    last_c    = float(close.iloc[-1])
    last_e50  = float(ema50.iloc[-1])
    last_e200 = float(ema200.iloc[-1])

    structure = market_structure(df_h1, lookback=40)

    if last_c > last_e50 > last_e200:
        ema_bias = "BULLISH"
    elif last_c < last_e50 < last_e200:
        ema_bias = "BEARISH"
    else:
        ema_bias = "NEUTRAL"

    if structure == "UPTREND" and ema_bias in ("BULLISH", "NEUTRAL"):
        bias = "UPTREND"
    elif structure == "DOWNTREND" and ema_bias in ("BEARISH", "NEUTRAL"):
        bias = "DOWNTREND"
    elif structure == "UPTREND" and ema_bias == "BULLISH":
        bias = "UPTREND"
    elif structure == "DOWNTREND" and ema_bias == "BEARISH":
        bias = "DOWNTREND"
    else:
        bias = "SIDEWAYS"

    return bias, {
        "h1_structure": structure,
        "h1_ema_bias":  ema_bias,
        "h1_ema50":     round(last_e50, 2),
        "h1_ema200":    round(last_e200, 2),
    }


# ── Layer 3: M15 Zone Finding ─────────────────────────────────

def _m15_in_zone(df_h1, df_m15, price: float, direction: str) -> tuple:
    """
    Returns (in_zone, info_dict)
    Confluence ≥ 2 from: M15 S/R, H1 S/R, M15 EMA50, H1 Fibonacci, Psych level.
    Tighter tolerance (0.003) for intraday zones.
    """
    confluence = []

    # M15 primary intraday zones
    m15_supports    = find_support_zones(df_m15, n=6, lookback=80)
    m15_resistances = find_resistance_zones(df_m15, n=6, lookback=80)

    if direction == "BUY" and price_near_zone(price, m15_supports, tolerance_pct=0.003):
        confluence.append("M15 support")
    if direction == "SELL" and price_near_zone(price, m15_resistances, tolerance_pct=0.003):
        confluence.append("M15 resistance")

    # H1 higher-timeframe context zones
    h1_supports    = find_support_zones(df_h1, n=4, lookback=60)
    h1_resistances = find_resistance_zones(df_h1, n=4, lookback=60)

    if direction == "BUY" and price_near_zone(price, h1_supports, tolerance_pct=0.004):
        confluence.append("H1 support")
    if direction == "SELL" and price_near_zone(price, h1_resistances, tolerance_pct=0.004):
        confluence.append("H1 resistance")

    # M15 EMA50
    m15_ema50 = float(ema(df_m15["close"], 50).iloc[-1])
    if m15_ema50 > 0 and abs(price - m15_ema50) / m15_ema50 <= 0.003:
        confluence.append("M15 EMA50")

    # Fibonacci from H1 recent swing (0.382, 0.5, 0.618)
    h1_sw_lows  = swing_lows(df_h1, left=5, right=3)
    h1_sw_highs = swing_highs(df_h1, left=5, right=3)
    sw_low_prices  = df_h1["low"][h1_sw_lows].values
    sw_high_prices = df_h1["high"][h1_sw_highs].values
    fib_hit = None
    if len(sw_low_prices) >= 1 and len(sw_high_prices) >= 1:
        recent_low  = float(sw_low_prices[-1])
        recent_high = float(sw_high_prices[-1])
        if recent_high > recent_low:
            fibs    = fibonacci_levels(recent_low, recent_high)
            key_fib = {k: v for k, v in fibs.items() if k in ("0.382", "0.500", "0.618")}
            fib_hit = find_fib_zone(price, key_fib, tolerance_pct=0.003)
            if fib_hit:
                confluence.append(f"Fibo {fib_hit}")

    # Psychological round number ($10 increments for gold)
    rounded = round(price / 10) * 10
    if rounded > 0 and abs(price - rounded) / rounded <= 0.001:
        confluence.append("Psych level")

    in_zone = len(confluence) >= 2

    return in_zone, {
        "confluence":        confluence,
        "confluence_count":  len(confluence),
        "m15_supports":      m15_supports[-3:] if m15_supports else [],
        "m15_resistances":   m15_resistances[-3:] if m15_resistances else [],
        "fib_hit":           fib_hit,
        "m15_ema50":         round(m15_ema50, 2),
    }


# ── Layer 4: M5 Setup Confirmation ────────────────────────────

def _m5_setup(df_m5, direction: str) -> tuple:
    """
    Returns (confirmed, signal_type, info_dict)
    PA patterns on M5 confirming the intraday setup is forming.
    RSI < 50 / > 50 as supporting indicator only.
    """
    signals = []

    if direction == "BUY":
        if is_pin_bar_bullish(df_m5):
            signals.append("pin_bar")
        if is_bullish_engulfing(df_m5):
            signals.append("engulfing")
        if is_morning_star(df_m5):
            signals.append("morning_star")
        if break_of_structure_bullish(df_m5, lookback=20):
            signals.append("bos")
    else:
        if is_pin_bar_bearish(df_m5):
            signals.append("pin_bar_bear")
        if is_bearish_engulfing(df_m5):
            signals.append("engulfing_bear")
        if break_of_structure_bearish(df_m5, lookback=20):
            signals.append("bos_bear")

    rsi_val = float(rsi(df_m5["close"]).iloc[-1])
    if direction == "BUY" and rsi_val < 50:
        signals.append("rsi_ok")
    elif direction == "SELL" and rsi_val > 50:
        signals.append("rsi_ok")

    pa_signals = [s for s in signals if s != "rsi_ok"]
    confirmed  = len(pa_signals) >= 1

    return confirmed, (pa_signals[0] if pa_signals else "none"), {
        "m5_signals": signals,
        "m5_rsi":     round(rsi_val, 1),
    }


# ── Layer 5: M1 Precise Entry Timing ─────────────────────────

def _m1_entry_timing(df_m1, direction: str) -> tuple:
    """
    Returns (confirmed, info_dict)
    Micro PA on M1 for precise entry after M5 setup is confirmed.
    Strict RSI: < 35 (BUY) / > 65 (SELL) to filter M1 noise.
    """
    signals = []
    rsi_val = float(rsi(df_m1["close"]).iloc[-1])

    if direction == "BUY":
        if is_pin_bar_bullish(df_m1):
            signals.append("m1_pin_bar")
        if is_bullish_engulfing(df_m1):
            signals.append("m1_engulfing")
        if break_of_structure_bullish(df_m1, lookback=15):
            signals.append("m1_bos")
        if rsi_val < 35:
            signals.append("m1_rsi_ok")
    else:
        if is_pin_bar_bearish(df_m1):
            signals.append("m1_pin_bar_bear")
        if is_bearish_engulfing(df_m1):
            signals.append("m1_engulfing_bear")
        if break_of_structure_bearish(df_m1, lookback=15):
            signals.append("m1_bos_bear")
        if rsi_val > 65:
            signals.append("m1_rsi_ok")

    pa_signals = [s for s in signals if "rsi" not in s]
    confirmed  = len(pa_signals) >= 1

    return confirmed, {
        "m1_signals": signals,
        "m1_rsi":     round(rsi_val, 1),
    }


# ── Layer 6: SL / TP / R:R (Intraday) ────────────────────────

def _sl_tp_rr(df_m5, df_m15, direction: str, entry: float) -> tuple:
    """
    SL: below/above M5 swing low/high (tighter intraday stop)
    TP: nearest M15 resistance/support level
    ATR from M5. Fallback: 2.0× ATR if no structural level found.
    Min R:R 1.5 enforced by caller.
    """
    atr_val = float(calc_atr(df_m5).iloc[-1])
    sub_m5  = df_m5.tail(30).copy()

    if direction == "BUY":
        sl_mask   = swing_lows(sub_m5, left=3, right=2)
        sl_prices = sub_m5["low"][sl_mask].values
        if len(sl_prices) >= 1:
            sl = round(float(sl_prices[-1]) - atr_val * 0.3, 4)
        else:
            sl = round(entry - atr_val * 1.2, 4)
        sl = min(sl, round(entry - atr_val * 0.8, 4))

        m15_res   = find_resistance_zones(df_m15, n=6, lookback=80)
        tp_target = nearest_resistance_above(entry, m15_res)
        tp = round(tp_target if tp_target else entry + atr_val * 2.0, 4)

    else:
        sh_mask   = swing_highs(sub_m5, left=3, right=2)
        sh_prices = sub_m5["high"][sh_mask].values
        if len(sh_prices) >= 1:
            sl = round(float(sh_prices[-1]) + atr_val * 0.3, 4)
        else:
            sl = round(entry + atr_val * 1.2, 4)
        sl = max(sl, round(entry + atr_val * 0.8, 4))

        m15_sup   = find_support_zones(df_m15, n=6, lookback=80)
        tp_target = nearest_support_below(entry, m15_sup)
        tp = round(tp_target if tp_target else entry - atr_val * 2.0, 4)

    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr      = round(tp_dist / sl_dist, 2) if sl_dist > 1e-10 else 0.0

    return sl, tp, rr


# ── Entry Strategies ──────────────────────────────────────────

def _pullback_buy(df_h4, df_h1, df_m15, df_m5, df_m1, ask: float) -> tuple:
    """H1 uptrend + M15 pullback to support zone + M5 setup + M1 precise entry."""
    h4_bias_str = _h4_bias(df_h4) if df_h4 is not None else "NEUTRAL"

    h1_bias, h1_info = _h1_trend(df_h1)
    if h1_bias != "UPTREND":
        return "NO TRADE", {**h1_info, "reason": f"H1 not uptrend ({h1_bias})"}
    if h4_bias_str == "BEAR":
        return "NO TRADE", {**h1_info, "reason": "H4 bearish — counter-trend skip"}

    in_zone, zone_info = _m15_in_zone(df_h1, df_m15, ask, "BUY")
    if not in_zone:
        return "NO TRADE", {**h1_info, **zone_info,
                            "reason": f"Not in M15 buy zone (confluence={zone_info['confluence_count']})"}

    confirmed, sig_type, m5_info = _m5_setup(df_m5, "BUY")
    if not confirmed:
        return "NO TRADE", {**h1_info, **zone_info, **m5_info,
                            "reason": "No M5 buy setup"}

    m1_ok, m1_info = _m1_entry_timing(df_m1, "BUY") if df_m1 is not None else (True, {})
    if not m1_ok:
        return "NO TRADE", {**h1_info, **zone_info, **m5_info, **m1_info,
                            "reason": f"No M1 entry timing (signals={m1_info.get('m1_signals', [])})"}

    sl, tp, rr = _sl_tp_rr(df_m5, df_m15, "BUY", ask)
    if rr < 1.5:
        return "NO TRADE", {**h1_info, **zone_info, **m5_info, **m1_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "BUY", {
        **h1_info, **zone_info, **m5_info, **m1_info,
        "entry_type": "PULLBACK",
        "h4_bias":    h4_bias_str,
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"H1 uptrend (H4 {h4_bias_str}) + M15 zone ({zone_info['confluence']}) + M5 {sig_type} + M1 | R:R {rr}",
    }


def _pullback_sell(df_h4, df_h1, df_m15, df_m5, df_m1, bid: float) -> tuple:
    """H1 downtrend + M15 pullback to resistance + M5 setup + M1 precise entry."""
    h4_bias_str = _h4_bias(df_h4) if df_h4 is not None else "NEUTRAL"

    h1_bias, h1_info = _h1_trend(df_h1)
    if h1_bias != "DOWNTREND":
        return "NO TRADE", {**h1_info, "reason": f"H1 not downtrend ({h1_bias})"}
    if h4_bias_str == "BULL":
        return "NO TRADE", {**h1_info, "reason": "H4 bullish — counter-trend skip"}

    in_zone, zone_info = _m15_in_zone(df_h1, df_m15, bid, "SELL")
    if not in_zone:
        return "NO TRADE", {**h1_info, **zone_info,
                            "reason": f"Not in M15 sell zone (confluence={zone_info['confluence_count']})"}

    confirmed, sig_type, m5_info = _m5_setup(df_m5, "SELL")
    if not confirmed:
        return "NO TRADE", {**h1_info, **zone_info, **m5_info,
                            "reason": "No M5 sell setup"}

    m1_ok, m1_info = _m1_entry_timing(df_m1, "SELL") if df_m1 is not None else (True, {})
    if not m1_ok:
        return "NO TRADE", {**h1_info, **zone_info, **m5_info, **m1_info,
                            "reason": f"No M1 entry timing (signals={m1_info.get('m1_signals', [])})"}

    sl, tp, rr = _sl_tp_rr(df_m5, df_m15, "SELL", bid)
    if rr < 1.5:
        return "NO TRADE", {**h1_info, **zone_info, **m5_info, **m1_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "SELL", {
        **h1_info, **zone_info, **m5_info, **m1_info,
        "entry_type": "PULLBACK_SELL",
        "h4_bias":    h4_bias_str,
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"H1 downtrend (H4 {h4_bias_str}) + M15 zone ({zone_info['confluence']}) + M5 {sig_type} + M1 | R:R {rr}",
    }


def _breakout_retest_buy(df_h4, df_h1, df_m15, df_m5, df_m1, ask: float) -> tuple:
    """H1 breaks resistance → retests from above → M5 + M1 confirm."""
    h4_bias_str = _h4_bias(df_h4) if df_h4 is not None else "NEUTRAL"
    h1_bias, h1_info = _h1_trend(df_h1)

    if h1_bias not in ("UPTREND", "SIDEWAYS"):
        return "NO TRADE", {**h1_info, "reason": "H1 not suitable for breakout buy"}

    h1_res = find_resistance_zones(df_h1, n=6, lookback=60)
    retest_zones = [z for z in h1_res if ask > z and abs(ask - z) / z <= 0.004]

    if not retest_zones:
        return "NO TRADE", {**h1_info, "reason": "No H1 breakout retest zone found"}

    confirmed, sig_type, m5_info = _m5_setup(df_m5, "BUY")
    if not confirmed:
        return "NO TRADE", {**h1_info, **m5_info,
                            "reason": "No M5 confirmation on H1 retest"}

    m1_ok, m1_info = _m1_entry_timing(df_m1, "BUY") if df_m1 is not None else (True, {})
    if not m1_ok:
        return "NO TRADE", {**h1_info, **m5_info, **m1_info,
                            "reason": f"No M1 entry timing on retest (signals={m1_info.get('m1_signals', [])})"}

    sl, tp, rr = _sl_tp_rr(df_m5, df_m15, "BUY", ask)
    if rr < 1.5:
        return "NO TRADE", {**h1_info, **m5_info, **m1_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "BUY", {
        **h1_info, **m5_info, **m1_info,
        "entry_type":  "BREAKOUT_RETEST",
        "h4_bias":     h4_bias_str,
        "retest_zone": retest_zones[-1],
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"H1 breakout retest at {retest_zones[-1]} + M5 {sig_type} + M1 | R:R {rr}",
    }


def _range_support_buy(df_h4, df_h1, df_m15, df_m5, df_m1, ask: float) -> tuple:
    """H1 sideways + price at M15 range support + M5 + M1 reversal."""
    h4_bias_str = _h4_bias(df_h4) if df_h4 is not None else "NEUTRAL"
    h1_bias, h1_info = _h1_trend(df_h1)

    if h1_bias != "SIDEWAYS":
        return "NO TRADE", {**h1_info, "reason": f"H1 not sideways ({h1_bias})"}

    m15_supports = find_support_zones(df_m15, n=6, lookback=80)
    if not price_near_zone(ask, m15_supports, tolerance_pct=0.003):
        return "NO TRADE", {**h1_info, "reason": "Not near M15 range support"}

    confirmed, sig_type, m5_info = _m5_setup(df_m5, "BUY")
    if not confirmed:
        return "NO TRADE", {**h1_info, **m5_info,
                            "reason": "No M5 reversal at range support"}

    m1_ok, m1_info = _m1_entry_timing(df_m1, "BUY") if df_m1 is not None else (True, {})
    if not m1_ok:
        return "NO TRADE", {**h1_info, **m5_info, **m1_info,
                            "reason": f"No M1 entry timing at range support (signals={m1_info.get('m1_signals', [])})"}

    sl, tp, rr = _sl_tp_rr(df_m5, df_m15, "BUY", ask)
    if rr < 1.5:
        return "NO TRADE", {**h1_info, **m5_info, **m1_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "BUY", {
        **h1_info, **m5_info, **m1_info,
        "entry_type": "RANGE_SUPPORT",
        "h4_bias":    h4_bias_str,
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"M15 range support + M5 {sig_type} + M1 | R:R {rr}",
    }


# ── Main Signal Generator ─────────────────────────────────────

def generate_signal(df_h4, df_h1=None, df_m15=None, df_m5=None, df_m1=None, cfg=None, ask=0.0, bid=0.0):
    """
    Intraday pipeline: H4 bias → H1 trend → M15 zones → M5 setup → M1 entry → SL/TP/R:R

    H4 is a soft counter-trend filter (BEAR skips BUY, BULL skips SELL).
    df_m1 is optional — skipped gracefully if None or insufficient bars.

    Priority order:
      1. Pullback Buy  (H1 uptrend — highest win rate)
      2. Pullback Sell (H1 downtrend)
      3. Breakout Retest Buy
      4. Range Support Buy
    """
    cfg = cfg or {}

    if df_h1 is None or df_m15 is None or df_m5 is None:
        return "NO TRADE", {"reason": "Missing H1, M15, or M5 data"}

    if len(df_h1) < 50 or len(df_m15) < 50 or len(df_m5) < 20:
        return "NO TRADE", {"reason": "Insufficient candle data"}

    if df_m1 is not None and len(df_m1) < 15:
        df_m1 = None  # too few bars — skip rather than error

    min_vol = cfg.get("min_volatility", 0.3)
    max_vol = cfg.get("max_volatility", 8.0)
    atr_val = round(float(calc_atr(df_m5).iloc[-1]), 4)

    if atr_val < min_vol:
        return "NO TRADE", {"atr_m5": atr_val, "reason": f"Market too quiet (ATR {atr_val})"}
    if atr_val > max_vol:
        return "NO TRADE", {"atr_m5": atr_val, "reason": f"Too volatile / news spike (ATR {atr_val})"}

    base = {"atr_m5": atr_val}

    sig, info = _pullback_buy(df_h4, df_h1, df_m15, df_m5, df_m1, ask)
    if sig == "BUY":
        return "BUY", {**base, **info}

    sig, info = _pullback_sell(df_h4, df_h1, df_m15, df_m5, df_m1, bid)
    if sig == "SELL":
        return "SELL", {**base, **info}

    sig, info = _breakout_retest_buy(df_h4, df_h1, df_m15, df_m5, df_m1, ask)
    if sig == "BUY":
        return "BUY", {**base, **info}

    sig, info = _range_support_buy(df_h4, df_h1, df_m15, df_m5, df_m1, ask)
    if sig == "BUY":
        return "BUY", {**base, **info}

    return "NO TRADE", {**base, **info, "reason": info.get("reason", "No valid setup")}
