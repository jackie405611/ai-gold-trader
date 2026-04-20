# ============================================================
#  lib/ai_macd_rsi.py  —  MACD + RSI Reversal Strategy
#
#  BUY conditions (ทั้งสองต้องผ่าน):
#    1. M5 RSI < rsi_oversold (38)  → ตลาด oversold กำลังจะกลับตัว
#    2. MACD line (EMA12-EMA26) ตัดขึ้นเหนือ Signal line (EMA9)
#       AND MACD < 0                → crossover ใต้ zero line (แรงกว่า)
#
#  SELL conditions (mirror):
#    1. M5 RSI > rsi_overbought (62) → ตลาด overbought กำลังจะกลับตัว
#    2. MACD line ตัดลงใต้ Signal line
#       AND MACD > 0                → crossover เหนือ zero line
#
#  Entry timing (M1):
#    - BUY  : M1 RSI กำลังพลิกตัวขึ้นจาก oversold (RSI เริ่มเพิ่มขึ้น)
#    - SELL : M1 RSI กำลังพลิกตัวลงจาก overbought (RSI เริ่มลดลง)
# ============================================================
import pandas as pd
try:
    from lib.indicators import ema, rsi as calc_rsi
except ImportError:
    from indicators import ema, rsi as calc_rsi


def _macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    คืน (macd_line, signal_line, histogram)
    macd_line   = EMA(fast) - EMA(slow)
    signal_line = EMA(macd_line, signal)
    histogram   = macd_line - signal_line
    slow ใช้ 26 ตามมาตรฐาน (เดิม 30 ทำให้สัญญาณช้าเกินไป)
    """
    macd_line   = ema(s, fast) - ema(s, slow)
    signal_line = ema(macd_line, signal)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def _macd_crossover(macd_line: pd.Series, signal_line: pd.Series,
                    lookback: int = 3) -> tuple[bool, bool]:
    """
    ตรวจจับ crossover ย้อนหลัง lookback แท่ง
    ป้องกันพลาด crossover ที่เกิดขึ้น 1-2 แท่งก่อนหน้า
    """
    bullish_cross = False
    bearish_cross = False
    for i in range(1, lookback + 1):
        prev = macd_line.iloc[-(i+1)] - signal_line.iloc[-(i+1)]
        curr = macd_line.iloc[-i]     - signal_line.iloc[-i]
        if prev < 0 and curr >= 0:
            bullish_cross = True
        if prev > 0 and curr <= 0:
            bearish_cross = True
    return bullish_cross, bearish_cross


def _m1_rsi_turning_up(df_m1: pd.DataFrame, rsi_period: int = 14,
                        lookback: int = 3) -> bool:
    """M1 RSI กำลังพลิกตัวขึ้น: current > prev[-lookback] AND current < 60"""
    rsi_s = calc_rsi(df_m1["close"], rsi_period)
    if len(rsi_s) < lookback + 1:
        return False
    current = rsi_s.iloc[-1]
    prev    = rsi_s.iloc[-(lookback + 1)]
    return (current > prev) and (current < 60)


def _m1_rsi_turning_down(df_m1: pd.DataFrame, rsi_period: int = 14,
                          lookback: int = 3) -> bool:
    """M1 RSI กำลังพลิกตัวลง: current < prev[-lookback] AND current > 40"""
    rsi_s = calc_rsi(df_m1["close"], rsi_period)
    if len(rsi_s) < lookback + 1:
        return False
    current = rsi_s.iloc[-1]
    prev    = rsi_s.iloc[-(lookback + 1)]
    return (current < prev) and (current > 40)


# ── Main ──────────────────────────────────────────────────────

def macd_rsi_signal(df_m5: pd.DataFrame, df_m1: pd.DataFrame | None = None,
                    cfg: dict | None = None) -> tuple[str, dict]:
    """Returns ("BUY" | "SELL" | "NO TRADE", info_dict)"""
    cfg    = cfg or {}
    rsi_os = cfg.get("rsi_oversold",   38)
    rsi_ob = cfg.get("rsi_overbought", 62)

    close = df_m5["close"]

    rsi_series             = calc_rsi(close)
    macd_line, sig_line, _ = _macd(close)

    m5_rsi     = round(rsi_series.iloc[-1], 1)
    macd_val   = round(macd_line.iloc[-1], 5)
    signal_val = round(sig_line.iloc[-1], 5)

    bullish_cross, bearish_cross = _macd_crossover(macd_line, sig_line, lookback=3)

    info = {
        "strategy":    "MACD_RSI",
        "m5_rsi":      m5_rsi,
        "macd":        macd_val,
        "macd_signal": signal_val,
        "macd_cross":  "bullish" if bullish_cross else ("bearish" if bearish_cross else "none"),
    }

    # ── BUY conditions ──
    rsi_oversold = m5_rsi < rsi_os
    macd_bull_ok = bullish_cross and (macd_val < 0)

    if rsi_oversold and macd_bull_ok:
        if df_m1 is not None:
            m1_turning = _m1_rsi_turning_up(df_m1)
            info["m1_entry"] = "turning_up" if m1_turning else "not_ready"
            if not m1_turning:
                return "NO TRADE", {**info, "reason": "M1 RSI ยังไม่กลับตัว (รอจังหวะเข้า BUY)"}
        return "BUY", {**info, "reason": f"RSI oversold({m5_rsi}) + MACD bullish cross below 0"}

    # ── SELL conditions ──
    rsi_overbought = m5_rsi > rsi_ob
    macd_bear_ok   = bearish_cross and (macd_val > 0)

    if rsi_overbought and macd_bear_ok:
        if df_m1 is not None:
            m1_turning = _m1_rsi_turning_down(df_m1)
            info["m1_entry"] = "turning_down" if m1_turning else "not_ready"
            if not m1_turning:
                return "NO TRADE", {**info, "reason": "M1 RSI ยังไม่กลับตัว (รอจังหวะเข้า SELL)"}
        return "SELL", {**info, "reason": f"RSI overbought({m5_rsi}) + MACD bearish cross above 0"}

    # ── ไม่มีสัญญาณ ──
    reasons = []
    if not rsi_oversold and not rsi_overbought:
        reasons.append(f"RSI neutral ({m5_rsi})")
    if not bullish_cross and not bearish_cross:
        reasons.append("No MACD crossover")
    elif bullish_cross and not macd_bull_ok:
        reasons.append(f"MACD cross but above 0 ({macd_val:.5f})")
    elif bearish_cross and not macd_bear_ok:
        reasons.append(f"MACD cross but below 0 ({macd_val:.5f})")

    return "NO TRADE", {**info, "reason": " | ".join(reasons) or "No signal"}
