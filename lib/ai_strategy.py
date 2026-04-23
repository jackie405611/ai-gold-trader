# ============================================================
#  lib/ai_strategy.py  —  5-Layer Gold Futures Entry Strategy
#
#  Layer 1 (H4): Big picture — UPTREND / DOWNTREND / SIDEWAYS
#  Layer 2 (H1): Zone finding — S/R + Fibo + EMA confluence
#  Layer 3 (M15): Entry confirmation — Price action + BOS
#  Layer 4: Stop Loss — below swing low / above swing high
#  Layer 5: R:R check — minimum 1:2 before entry allowed
#
#  Entry types:
#    PULLBACK       — H4 uptrend + H1 pulls back to support zone
#    PULLBACK_SELL  — H4 downtrend + H1 pulls back to resistance
#    BREAKOUT_RETEST — H4/H1 breaks level + retests from other side
#    RANGE_SUPPORT  — H4 sideways + price at range support
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


# ── Layer 1: H4 Big Picture ───────────────────────────────────

def _h4_structure(df_h4) -> tuple:
    """
    Returns (bias, info_dict)
    bias: "UPTREND" | "DOWNTREND" | "SIDEWAYS"
    Combines HH/HL structure with EMA50/200 position.
    """
    close     = df_h4["close"]
    ema50     = ema(close, 50)
    ema200    = ema(close, 200)
    last_c    = float(close.iloc[-1])
    last_e50  = float(ema50.iloc[-1])
    last_e200 = float(ema200.iloc[-1])

    structure = market_structure(df_h4, lookback=40)

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
        "h4_structure": structure,
        "h4_ema_bias":  ema_bias,
        "h4_ema50":     round(last_e50, 2),
        "h4_ema200":    round(last_e200, 2),
    }


# ── Layer 2: H1 Zone Finding ──────────────────────────────────

def _h1_in_zone(df_h4, df_h1, price: float, direction: str) -> tuple:
    """
    Returns (in_zone, info_dict)
    Confluence: price must be near 2+ of — H1 S/R, H4 S/R, H1 EMA50, Fibonacci key levels.
    direction: "BUY" checks support zones, "SELL" checks resistance zones.
    """
    confluence = []

    # H1 zones
    h1_supports    = find_support_zones(df_h1, n=6, lookback=80)
    h1_resistances = find_resistance_zones(df_h1, n=6, lookback=80)

    if direction == "BUY" and price_near_zone(price, h1_supports, tolerance_pct=0.004):
        confluence.append("H1 support")
    if direction == "SELL" and price_near_zone(price, h1_resistances, tolerance_pct=0.004):
        confluence.append("H1 resistance")

    # H4 zones
    h4_supports    = find_support_zones(df_h4, n=4, lookback=30)
    h4_resistances = find_resistance_zones(df_h4, n=4, lookback=30)

    if direction == "BUY" and price_near_zone(price, h4_supports, tolerance_pct=0.005):
        confluence.append("H4 support")
    if direction == "SELL" and price_near_zone(price, h4_resistances, tolerance_pct=0.005):
        confluence.append("H4 resistance")

    # H1 EMA50
    h1_ema50 = float(ema(df_h1["close"], 50).iloc[-1])
    if h1_ema50 > 0 and abs(price - h1_ema50) / h1_ema50 <= 0.004:
        confluence.append("H1 EMA50")

    # Fibonacci from H4 recent swing (0.382, 0.5, 0.618 only)
    h4_sw_lows  = swing_lows(df_h4, left=5, right=3)
    h4_sw_highs = swing_highs(df_h4, left=5, right=3)
    sw_low_prices  = df_h4["low"][h4_sw_lows].values
    sw_high_prices = df_h4["high"][h4_sw_highs].values
    fib_hit = None
    if len(sw_low_prices) >= 1 and len(sw_high_prices) >= 1:
        recent_low  = float(sw_low_prices[-1])
        recent_high = float(sw_high_prices[-1])
        if recent_high > recent_low:
            fibs    = fibonacci_levels(recent_low, recent_high)
            key_fib = {k: v for k, v in fibs.items() if k in ("0.382", "0.500", "0.618")}
            fib_hit = find_fib_zone(price, key_fib, tolerance_pct=0.004)
            if fib_hit:
                confluence.append(f"Fibo {fib_hit}")

    # Psychological round number (gold moves in $10 increments)
    rounded = round(price / 10) * 10
    if rounded > 0 and abs(price - rounded) / rounded <= 0.001:
        confluence.append("Psych level")

    in_zone = len(confluence) >= 2

    return in_zone, {
        "confluence":       confluence,
        "confluence_count": len(confluence),
        "h1_supports":      h1_supports[-3:] if h1_supports else [],
        "h1_resistances":   h1_resistances[-3:] if h1_resistances else [],
        "fib_hit":          fib_hit,
        "h1_ema50":         round(h1_ema50, 2),
    }


# ── Layer 3: M15 Entry Confirmation ───────────────────────────

def _m15_confirmation(df_m15, direction: str) -> tuple:
    """
    Returns (confirmed, signal_type, info_dict)
    Checks price action patterns + BOS for entry timing.
    """
    signals = []

    if direction == "BUY":
        if is_pin_bar_bullish(df_m15):
            signals.append("pin_bar")
        if is_bullish_engulfing(df_m15):
            signals.append("engulfing")
        if is_morning_star(df_m15):
            signals.append("morning_star")
        if break_of_structure_bullish(df_m15, lookback=20):
            signals.append("bos")
    else:  # SELL
        if is_pin_bar_bearish(df_m15):
            signals.append("pin_bar_bear")
        if is_bearish_engulfing(df_m15):
            signals.append("engulfing_bear")
        if break_of_structure_bearish(df_m15, lookback=20):
            signals.append("bos_bear")

    # RSI as supporting indicator (not standalone)
    rsi_val = float(rsi(df_m15["close"]).iloc[-1])
    if direction == "BUY" and rsi_val < 50:
        signals.append("rsi_ok")
    elif direction == "SELL" and rsi_val > 50:
        signals.append("rsi_ok")

    # Need at least 1 price action signal (not just rsi_ok)
    pa_signals = [s for s in signals if s != "rsi_ok"]
    confirmed  = len(pa_signals) >= 1

    return confirmed, (pa_signals[0] if pa_signals else "none"), {
        "m15_signals": signals,
        "m15_rsi":     round(rsi_val, 1),
    }


# ── Layer 4+5: SL / TP / R:R ──────────────────────────────────

def _sl_tp_rr(df_m15, df_h1, direction: str, entry: float) -> tuple:
    """
    Returns (sl, tp, rr_ratio)
    SL: below swing low (BUY) or above swing high (SELL) on M15
    TP: nearest H1 resistance above (BUY) or support below (SELL)
        fallback to 2.5× ATR if no structural level found
    Minimum R:R = 1.5 enforced by caller.
    """
    atr_val  = float(calc_atr(df_m15).iloc[-1])
    sub_m15  = df_m15.tail(30).copy()

    if direction == "BUY":
        sl_mask   = swing_lows(sub_m15, left=3, right=2)
        sl_prices = sub_m15["low"][sl_mask].values
        if len(sl_prices) >= 1:
            # SL just below the nearest swing low, with ATR buffer
            sl = round(float(sl_prices[-1]) - atr_val * 0.3, 4)
        else:
            sl = round(entry - atr_val * 1.5, 4)
        sl = min(sl, round(entry - atr_val, 4))  # never too close

        h1_res     = find_resistance_zones(df_h1, n=6, lookback=80)
        tp_target  = nearest_resistance_above(entry, h1_res)
        tp = round(tp_target if tp_target else entry + atr_val * 2.5, 4)

    else:  # SELL
        sh_mask   = swing_highs(sub_m15, left=3, right=2)
        sh_prices = sub_m15["high"][sh_mask].values
        if len(sh_prices) >= 1:
            sl = round(float(sh_prices[-1]) + atr_val * 0.3, 4)
        else:
            sl = round(entry + atr_val * 1.5, 4)
        sl = max(sl, round(entry + atr_val, 4))

        h1_sup    = find_support_zones(df_h1, n=6, lookback=80)
        tp_target = nearest_support_below(entry, h1_sup)
        tp = round(tp_target if tp_target else entry - atr_val * 2.5, 4)

    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    rr      = round(tp_dist / sl_dist, 2) if sl_dist > 1e-10 else 0.0

    return sl, tp, rr


# ── Entry Strategies ──────────────────────────────────────────

def _pullback_buy(df_h4, df_h1, df_m15, ask: float) -> tuple:
    """H4 uptrend + H1 pulls back to support zone + M15 reversal."""
    h4_bias, h4_info = _h4_structure(df_h4)
    if h4_bias != "UPTREND":
        return "NO TRADE", {**h4_info, "reason": f"H4 not uptrend ({h4_bias})"}

    in_zone, zone_info = _h1_in_zone(df_h4, df_h1, ask, "BUY")
    if not in_zone:
        return "NO TRADE", {**h4_info, **zone_info,
                            "reason": f"Not in buy zone (confluence={zone_info['confluence_count']})"}

    confirmed, sig_type, m15_info = _m15_confirmation(df_m15, "BUY")
    if not confirmed:
        return "NO TRADE", {**h4_info, **zone_info, **m15_info,
                            "reason": "No M15 buy confirmation"}

    sl, tp, rr = _sl_tp_rr(df_m15, df_h1, "BUY", ask)
    if rr < 1.5:
        return "NO TRADE", {**h4_info, **zone_info, **m15_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "BUY", {
        **h4_info, **zone_info, **m15_info,
        "entry_type": "PULLBACK",
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"H4 uptrend + zone ({zone_info['confluence']}) + M15 {sig_type} | R:R {rr}",
    }


def _pullback_sell(df_h4, df_h1, df_m15, bid: float) -> tuple:
    """H4 downtrend + H1 pulls back to resistance zone + M15 reversal."""
    h4_bias, h4_info = _h4_structure(df_h4)
    if h4_bias != "DOWNTREND":
        return "NO TRADE", {**h4_info, "reason": f"H4 not downtrend ({h4_bias})"}

    in_zone, zone_info = _h1_in_zone(df_h4, df_h1, bid, "SELL")
    if not in_zone:
        return "NO TRADE", {**h4_info, **zone_info,
                            "reason": f"Not in sell zone (confluence={zone_info['confluence_count']})"}

    confirmed, sig_type, m15_info = _m15_confirmation(df_m15, "SELL")
    if not confirmed:
        return "NO TRADE", {**h4_info, **zone_info, **m15_info,
                            "reason": "No M15 sell confirmation"}

    sl, tp, rr = _sl_tp_rr(df_m15, df_h1, "SELL", bid)
    if rr < 1.5:
        return "NO TRADE", {**h4_info, **zone_info, **m15_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "SELL", {
        **h4_info, **zone_info, **m15_info,
        "entry_type": "PULLBACK_SELL",
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"H4 downtrend + zone ({zone_info['confluence']}) + M15 {sig_type} | R:R {rr}",
    }


def _breakout_retest_buy(df_h4, df_h1, df_m15, ask: float) -> tuple:
    """
    H4/H1 breaks resistance → price retests old resistance (now support) → M15 confirms.
    Detected by: price is just above a known H1 resistance level (within 0.5%).
    """
    h4_bias, h4_info = _h4_structure(df_h4)
    if h4_bias not in ("UPTREND", "SIDEWAYS"):
        return "NO TRADE", {**h4_info, "reason": "H4 not suitable for breakout buy"}

    h1_res = find_resistance_zones(df_h1, n=6, lookback=80)
    # A broken resistance becomes support — price is above it within tolerance
    retest_zones = [z for z in h1_res if ask > z and abs(ask - z) / z <= 0.005]

    if not retest_zones:
        return "NO TRADE", {**h4_info, "reason": "No breakout retest zone found"}

    confirmed, sig_type, m15_info = _m15_confirmation(df_m15, "BUY")
    if not confirmed:
        return "NO TRADE", {**h4_info, **m15_info,
                            "reason": "No M15 confirmation on retest"}

    sl, tp, rr = _sl_tp_rr(df_m15, df_h1, "BUY", ask)
    if rr < 1.5:
        return "NO TRADE", {**h4_info, **m15_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "BUY", {
        **h4_info, **m15_info,
        "entry_type":   "BREAKOUT_RETEST",
        "retest_zone":  retest_zones[-1],
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"Breakout retest at {retest_zones[-1]} + M15 {sig_type} | R:R {rr}",
    }


def _range_support_buy(df_h4, df_h1, df_m15, ask: float) -> tuple:
    """H4 sideways + price at range support + M15 reversal."""
    h4_bias, h4_info = _h4_structure(df_h4)
    if h4_bias != "SIDEWAYS":
        return "NO TRADE", {**h4_info, "reason": f"H4 not sideways ({h4_bias})"}

    h1_supports = find_support_zones(df_h1, n=6, lookback=80)
    if not price_near_zone(ask, h1_supports, tolerance_pct=0.004):
        return "NO TRADE", {**h4_info, "reason": "Not near range support"}

    confirmed, sig_type, m15_info = _m15_confirmation(df_m15, "BUY")
    if not confirmed:
        return "NO TRADE", {**h4_info, **m15_info,
                            "reason": "No M15 reversal at range support"}

    sl, tp, rr = _sl_tp_rr(df_m15, df_h1, "BUY", ask)
    if rr < 1.5:
        return "NO TRADE", {**h4_info, **m15_info,
                            "sl": sl, "tp": tp, "rr": rr,
                            "reason": f"R:R too low ({rr} < 1.5)"}

    return "BUY", {
        **h4_info, **m15_info,
        "entry_type": "RANGE_SUPPORT",
        "sl": sl, "tp": tp, "rr": rr,
        "reason": f"Range support + M15 {sig_type} | R:R {rr}",
    }


# ── Main Signal Generator ─────────────────────────────────────

def generate_signal(df_h4, df_h1=None, df_m15=None, cfg=None, ask=0.0, bid=0.0):
    """
    Input:  df_h4, df_h1, df_m15 DataFrames + current ask/bid prices
    Output: ("BUY" | "SELL" | "NO TRADE", info_dict)

    info_dict for BUY/SELL includes: sl, tp, rr, entry_type, reason, confluence

    Priority order:
      1. Pullback Buy  (H4 uptrend — highest win rate)
      2. Pullback Sell (H4 downtrend)
      3. Breakout Retest Buy
      4. Range Support Buy
    """
    cfg = cfg or {}

    if df_h1 is None or df_m15 is None:
        return "NO TRADE", {"reason": "Missing H1 or M15 data"}

    if len(df_h4) < 50 or len(df_h1) < 50 or len(df_m15) < 20:
        return "NO TRADE", {"reason": "Insufficient candle data"}

    min_vol = cfg.get("min_volatility", 0.3)
    max_vol = cfg.get("max_volatility", 8.0)
    atr_val = round(float(calc_atr(df_m15).iloc[-1]), 4)

    if atr_val < min_vol:
        return "NO TRADE", {"atr_m15": atr_val, "reason": f"Market too quiet (ATR {atr_val})"}
    if atr_val > max_vol:
        return "NO TRADE", {"atr_m15": atr_val, "reason": f"Too volatile / news spike (ATR {atr_val})"}

    base = {"atr_m15": atr_val}

    # 1. Pullback Buy — best setup when H4 is clearly bullish
    sig, info = _pullback_buy(df_h4, df_h1, df_m15, ask)
    if sig == "BUY":
        return "BUY", {**base, **info}

    # 2. Pullback Sell — H4 clearly bearish
    sig, info = _pullback_sell(df_h4, df_h1, df_m15, bid)
    if sig == "SELL":
        return "SELL", {**base, **info}

    # 3. Breakout + Retest Buy
    sig, info = _breakout_retest_buy(df_h4, df_h1, df_m15, ask)
    if sig == "BUY":
        return "BUY", {**base, **info}

    # 4. Range Support Buy
    sig, info = _range_support_buy(df_h4, df_h1, df_m15, ask)
    if sig == "BUY":
        return "BUY", {**base, **info}

    return "NO TRADE", {**base, **info, "reason": info.get("reason", "No valid setup")}
