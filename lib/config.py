# ============================================================
#  lib/config.py  —  AI Multi-Symbol Trader V3 (Vercel)
#  MT5 constants removed; Twelve Data symbol mapping added.
# ============================================================
import os

# ── Symbols ที่ต้องการเทรด ────────────────────────────────────
SYMBOLS = {
    "XAUUSDm": {
        "enabled":          True,
        "lot":              0.01,
        "max_spread":       30,        # points
        "atr_sl_mult":      1.5,       # ATR fallback SL (used if strategy SL unavailable)
        "atr_tp_mult":      2.5,       # ATR fallback TP
        "min_volatility":   1.0,       # M15 ATR minimum (too quiet = no trade)
        "max_volatility":   15.0,      # M15 ATR maximum (news spike = no trade)
        "zone_tolerance":   0.004,     # 0.4% price proximity to zone
        "min_rr":           1.5,       # minimum R:R required to enter
        "sessions":         [(7, 12), (13, 17)],  # UTC
        "label":            "GOLD",
    },
    "EURUSDm": {
        "enabled":          True,
        "lot":              0.01,
        "max_spread":       15,
        "atr_sl_mult":      1.5,
        "atr_tp_mult":      2.5,
        "min_volatility":   0.0003,
        "max_volatility":   0.005,
        "zone_tolerance":   0.003,
        "min_rr":           1.5,
        "sessions":         [(7, 17)],
        "label":            "EURUSD",
    },
    "BTCUSDm": {
        "enabled":          True,
        "lot":              0.01,
        "max_spread":       200,
        "atr_sl_mult":      1.5,
        "atr_tp_mult":      2.5,
        "min_volatility":   50.0,
        "max_volatility":   3000.0,
        "zone_tolerance":   0.005,
        "min_rr":           1.5,
        "sessions":         [(0, 24)],
        "label":            "BTC",
    },
}

# ── Twelve Data API symbol mapping ───────────────────────────
# Maps MT5 symbol names → Twelve Data API symbol names + metadata
SYMBOL_MAP = {
    "XAUUSDm": {
        "twelve_symbol": "XAU/USD",
        "point_value":   0.01,      # 1 point = $0.01
        "digits":        2,
    },
    "EURUSDm": {
        "twelve_symbol": "EUR/USD",
        "point_value":   0.00001,   # 1 pip = $0.00001
        "digits":        5,
    },
    "BTCUSDm": {
        "twelve_symbol": "BTC/USD",
        "twelve_exchange": "Coinbase Pro",   # ระบุ exchange ป้องกัน ambiguous symbol
        "point_value":   0.01,
        "digits":        2,
    },
}

# ── Tick values for dynamic lot calculation ──────────────────
# USD profit per 1 point move per 0.01 lot
TICK_VALUES = {
    "XAUUSDm":  1.0,    # $1 per $0.01 move per 0.01 lot (100 oz × 0.01 lot)
    "EURUSDm":  0.1,    # approx $0.10 per pip per 0.01 lot
    "BTCUSDm":  0.01,   # approx, varies with BTC price
}

# ── Global Risk ──────────────────────────────────────────────
MAX_DD               = 20        # % portfolio drawdown รวม
RISK_PER_TRADE       = 1.0       # % balance ต่อ 1 trade
USE_DYNAMIC_LOT      = True
MAX_CONSECUTIVE_LOSS = 3
MAX_DAILY_LOSS_PCT   = 5.0

# ── AI ───────────────────────────────────────────────────────
CONFIRM_BARS = 2

# ── Trailing Stop ────────────────────────────────────────────
USE_TRAILING_STOP = True
TRAILING_ATR_MULT = 1.0

# ── Session Filter ───────────────────────────────────────────
USE_SESSION_FILTER = True

# ── Telegram (read from environment variables) ───────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
