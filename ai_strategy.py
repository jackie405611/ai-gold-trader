# ai_strategy.py
import math
import pandas as pd

from ai_m5 import _adx
from ai_m1 import _rsi

VALID_MODES = {"auto", "pullback", "breakout", "range"}

def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def _atr(df, p=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def _last_swing_low(df, lookback=10):
    return float(df["low"].tail(lookback).min())

def _last_swing_high(df, lookback=10):
    return float(df["high"].tail(lookback).max())

def _bullish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    cur = df.iloc[-1]
    return (
        prev["close"] < prev["open"]
        and cur["close"] > cur["open"]
        and cur["open"] <= prev["close"]
        and cur["close"] >= prev["open"]
    )

def _bearish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    cur = df.iloc[-1]
    return (
        prev["close"] > prev["open"]
        and cur["close"] < cur["open"]
        and cur["open"] >= prev["close"]
        and cur["close"] <= prev["open"]
    )

def _pinbar_bull(df):
    c = df.iloc[-1]
    body = abs(c["close"] - c["open"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    upper_wick = c["high"] - max(c["open"], c["close"])
    return lower_wick > body * 1.5 and lower_wick > upper_wick

def _pinbar_bear(df):
    c = df.iloc[-1]
    body = abs(c["close"] - c["open"])
    upper_wick = c["high"] - max(c["open"], c["close"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    return upper_wick > body * 1.5 and upper_wick > lower_wick

def _break_of_structure_up(df, lookback=5):
    if len(df) < lookback + 2:
        return False
    prev_high = float(df["high"].iloc[-(lookback+1):-1].max())
    return float(df["close"].iloc[-1]) > prev_high

def _break_of_structure_down(df, lookback=5):
    if len(df) < lookback + 2:
        return False
    prev_low = float(df["low"].iloc[-(lookback+1):-1].min())
    return float(df["close"].iloc[-1]) < prev_low

def detect_regime(df_h1, cfg=None):
    cfg = cfg or {}
    atr_val = float(_atr(df_h1).iloc[-1])
    adx_s, plus_di, minus_di = _adx(df_h1)
    adx_val = float(adx_s.iloc[-1])

    min_vol = cfg.get("min_volatility", 0.3)
    max_vol = cfg.get("max_volatility", 8.0)
    adx_trend = cfg.get("adx_trend_threshold", 25)

    if atr_val > max_vol:
        regime = "VOLATILE"
    elif atr_val < min_vol:
        regime = "QUIET"
    elif adx_val >= adx_trend:
        regime = "TRENDING"
    else:
        regime = "RANGING"

    return {
        "regime": regime,
        "atr_h1": round(atr_val, 4),
        "adx_h1": round(adx_val, 2),
        "plus_di_h1": round(float(plus_di.iloc[-1]), 2),
        "minus_di_h1": round(float(minus_di.iloc[-1]), 2),
    }

def market_bias(df_h1, cfg=None):
    close = df_h1["close"]
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)

    last_close = float(close.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])

    hh = float(df_h1["high"].tail(20).max())
    ll = float(df_h1["low"].tail(20).min())

    if last_close > last_ema50 > last_ema200:
        side = "BUY"
    elif last_close < last_ema50 < last_ema200:
        side = "SELL"
    else:
        side = "NONE"

    return {
        "bias": side,
        "close_h1": round(last_close, 2),
        "ema50_h1": round(last_ema50, 2),
        "ema200_h1": round(last_ema200, 2),
        "range_high_20": round(hh, 2),
        "range_low_20": round(ll, 2),
    }

def pullback_zone(df_h1, bias):
    close = df_h1["close"]
    high = df_h1["high"]
    low = df_h1["low"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)

    last_price = float(close.iloc[-1])
    zone_mid = float(ema50.iloc[-1])
    zone_fast = float(ema20.iloc[-1])

    swing_high = float(high.tail(30).max())
    swing_low = float(low.tail(30).min())
    move = max(swing_high - swing_low, 1e-9)

    fib50 = swing_high - (move * 0.5)
    fib618 = swing_high - (move * 0.618)

    if bias == "BUY":
        zone_low = min(zone_mid, fib618)
        zone_high = max(zone_fast, fib50)
        in_zone = zone_low <= last_price <= zone_high
    elif bias == "SELL":
        sell_fib50 = swing_low + (move * 0.5)
        sell_fib618 = swing_low + (move * 0.618)
        zone_low = min(zone_fast, sell_fib50)
        zone_high = max(zone_mid, sell_fib618)
        in_zone = zone_low <= last_price <= zone_high
    else:
        zone_low = zone_high = last_price
        in_zone = False

    return {
        "zone_low": round(zone_low, 2),
        "zone_high": round(zone_high, 2),
        "in_zone": in_zone,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
    }

def confirm_pullback(df_m15, df_m5, df_m1, bias, cfg=None):
    cfg = cfg or {}
    rsi_m1 = _rsi(df_m1["close"])
    last_rsi = float(rsi_m1.iloc[-1])

    if bias == "BUY":
        confirm = (
            (_bullish_engulfing(df_m5) or _pinbar_bull(df_m5))
            and _break_of_structure_up(df_m1, lookback=5)
            and last_rsi <= cfg.get("rsi_pullback_buy_max", 45)
        )
        reason = "bullish engulfing/pinbar + M1 BOS up + RSI pullback"
    elif bias == "SELL":
        confirm = (
            (_bearish_engulfing(df_m5) or _pinbar_bear(df_m5))
            and _break_of_structure_down(df_m1, lookback=5)
            and last_rsi >= cfg.get("rsi_pullback_sell_min", 55)
        )
        reason = "bearish engulfing/pinbar + M1 BOS down + RSI pullback"
    else:
        confirm = False
        reason = "no bias"

    return {
        "confirmed": confirm,
        "rsi_m1": round(last_rsi, 2),
        "confirm_reason": reason,
    }

def breakout_retest_signal(df_h1, df_m15, df_m5, cfg=None):
    close_h1 = float(df_h1["close"].iloc[-1])
    prev_high = float(df_h1["high"].iloc[-21:-1].max())
    prev_low = float(df_h1["low"].iloc[-21:-1].min())
    atr_m15 = float(_atr(df_m15).iloc[-1])

    breakout_buffer = (cfg or {}).get("breakout_buffer_atr", 0.15)

    buy_break = close_h1 > prev_high + atr_m15 * breakout_buffer
    sell_break = close_h1 < prev_low - atr_m15 * breakout_buffer

    if buy_break:
        retest_ok = float(df_m15["low"].tail(3).min()) <= prev_high and float(df_m5["close"].iloc[-1]) > prev_high
        if retest_ok and (_bullish_engulfing(df_m5) or _pinbar_bull(df_m5)):
            return "BUY", {
                "strategy": "breakout",
                "level": round(prev_high, 2),
                "reason": "H1 breakout above resistance + retest held",
            }

    if sell_break:
        retest_ok = float(df_m15["high"].tail(3).max()) >= prev_low and float(df_m5["close"].iloc[-1]) < prev_low
        if retest_ok and (_bearish_engulfing(df_m5) or _pinbar_bear(df_m5)):
            return "SELL", {
                "strategy": "breakout",
                "level": round(prev_low, 2),
                "reason": "H1 breakdown below support + retest held",
            }

    return "NO TRADE", {
        "strategy": "breakout",
        "reason": "breakout/retest not confirmed",
        "resistance": round(prev_high, 2),
        "support": round(prev_low, 2),
    }

def range_reversal_signal(df_h1, df_m15, df_m5, cfg=None):
    cfg = cfg or {}
    hi = float(df_h1["high"].tail(30).max())
    lo = float(df_h1["low"].tail(30).min())
    last = float(df_h1["close"].iloc[-1])
    width = max(hi - lo, 1e-9)
    pos = (last - lo) / width

    rsi_m15 = float(_rsi(df_m15["close"]).iloc[-1])

    if pos <= cfg.get("range_buy_zone_max", 0.25):
        if (_bullish_engulfing(df_m5) or _pinbar_bull(df_m5)) and rsi_m15 <= cfg.get("range_rsi_buy_max", 40):
            return "BUY", {
                "strategy": "range",
                "reason": "near range support + bullish reversal",
                "range_high": round(hi, 2),
                "range_low": round(lo, 2),
            }

    if pos >= cfg.get("range_sell_zone_min", 0.75):
        if (_bearish_engulfing(df_m5) or _pinbar_bear(df_m5)) and rsi_m15 >= cfg.get("range_rsi_sell_min", 60):
            return "SELL", {
                "strategy": "range",
                "reason": "near range resistance + bearish reversal",
                "range_high": round(hi, 2),
                "range_low": round(lo, 2),
            }

    return "NO TRADE", {
        "strategy": "range",
        "reason": "price not at range edge or no reversal confirmation",
        "range_high": round(hi, 2),
        "range_low": round(lo, 2),
    }

def build_trade_plan(df_m15, signal, cfg=None):
    cfg = cfg or {}
    atr = float(_atr(df_m15).iloc[-1])
    entry = float(df_m15["close"].iloc[-1])

    sl_atr = cfg.get("atr_sl_mult", 1.5)
    tp_atr = cfg.get("atr_tp_mult", 2.5)

    if signal == "BUY":
        swing = _last_swing_low(df_m15, lookback=10)
        sl = min(swing, entry - atr * sl_atr)
        tp1 = entry + atr * tp_atr
        rr = (tp1 - entry) / max(entry - sl, 1e-9)
    else:
        swing = _last_swing_high(df_m15, lookback=10)
        sl = max(swing, entry + atr * sl_atr)
        tp1 = entry - atr * tp_atr
        rr = (entry - tp1) / max(sl - entry, 1e-9)

    return {
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": round(tp1, 2),
        "atr_m15": round(atr, 4),
        "rr": round(rr, 2),
    }

def analyze_signal(df_h1, df_m15, df_m5, df_m1, cfg=None, mode="auto"):
    cfg = cfg or {}
    mode = (mode or "auto").lower().strip()
    if mode not in VALID_MODES:
        mode = "auto"

    regime = detect_regime(df_h1, cfg)
    bias = market_bias(df_h1, cfg)
    zone = pullback_zone(df_h1, bias["bias"])
    confirm = confirm_pullback(df_m15, df_m5, df_m1, bias["bias"], cfg)

    info = {
        **regime,
        **bias,
        **zone,
        **confirm,
        "requested_mode": mode,
    }

    if regime["regime"] in {"VOLATILE", "QUIET"}:
        return "NO TRADE", {**info, "reason": f"regime={regime['regime']}"}

    # auto mode
    if mode == "auto":
        if regime["regime"] == "TRENDING":
            mode = "pullback"
        else:
            mode = "range"

    if mode == "pullback":
        if bias["bias"] in {"BUY", "SELL"} and zone["in_zone"] and confirm["confirmed"]:
            plan = build_trade_plan(df_m15, bias["bias"], cfg)
            return bias["bias"], {**info, **plan, "strategy": "pullback", "reason": "trend + zone + confirmation"}
        return "NO TRADE", {**info, "strategy": "pullback", "reason": "bias/zone/confirmation not complete"}

    if mode == "breakout":
        sig, extra = breakout_retest_signal(df_h1, df_m15, df_m5, cfg)
        if sig in {"BUY", "SELL"}:
            plan = build_trade_plan(df_m15, sig, cfg)
            return sig, {**info, **extra, **plan}
        return sig, {**info, **extra}

    if mode == "range":
        sig, extra = range_reversal_signal(df_h1, df_m15, df_m5, cfg)
        if sig in {"BUY", "SELL"}:
            plan = build_trade_plan(df_m15, sig, cfg)
            return sig, {**info, **extra, **plan}
        return sig, {**info, **extra}

    return "NO TRADE", {**info, "reason": "invalid mode"}

# backward-compatible alias
generate_signal = analyze_signal