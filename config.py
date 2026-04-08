# ============================================================
#  config.py  —  AI Multi-Symbol Trader V3
#  เพิ่ม/ลด symbol ใน SYMBOLS dict ได้เลย
#  ⚠️  เปลี่ยนค่า YOUR_ ก่อนรัน
# ============================================================

# ── Symbols ที่ต้องการเทรด ────────────────────────────────────
# "enabled": True  = เปิด trade อัตโนมัติ
# "enabled": False = วิเคราะห์ + แจ้งสัญญาณ แต่ไม่เปิด trade

SYMBOLS = {

    "XAUUSDm": {
        "enabled":        True,
        "lot":            0.01,
        "max_spread":     30,        # points
        "atr_sl_mult":    1.5,
        "atr_tp_mult":    2.5,
        "min_volatility": 0.3,       # ATR USD ขั้นต่ำ
        "max_volatility": 8.0,
        "rsi_oversold":   38,
        "rsi_overbought": 62,
        "sessions":       [(7, 12), (13, 17)],  # UTC
        "label":          "GOLD",
    },

    "EURUSDm": {
        "enabled":        True,
        "lot":            0.01,
        "max_spread":     15,
        "atr_sl_mult":    1.5,
        "atr_tp_mult":    2.5,
        "min_volatility": 0.0003,
        "max_volatility": 0.005,
        "rsi_oversold":   38,
        "rsi_overbought": 62,
        "sessions":       [(7, 17)],
        "label":          "EURUSD",
    },

    "BTCUSDm": {
        "enabled":        True,
        "lot":            0.01,
        "max_spread":     200,
        "atr_sl_mult":    1.5,
        "atr_tp_mult":    2.5,
        "min_volatility": 20.0,
        "max_volatility": 2000.0,
        "rsi_oversold":   38,
        "rsi_overbought": 62,
        "sessions":       [(0, 24)],   # 24 ชั่วโมง
        "label":          "BTC",
    },
}

# ── Global Risk ──────────────────────────────────────────────
MAX_DD           = 20        # % portfolio drawdown รวม
RISK_PER_TRADE   = 1.0       # % balance ต่อ 1 trade
USE_DYNAMIC_LOT  = True

# ── AI ───────────────────────────────────────────────────────
CONFIRM_BARS     = 2

# ── Trailing Stop ────────────────────────────────────────────
USE_TRAILING_STOP = True
TRAILING_ATR_MULT = 1.0

# ── Session Filter ───────────────────────────────────────────
USE_SESSION_FILTER = True

# ── Loop ─────────────────────────────────────────────────────
LOOP_SECONDS = 60

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8446348432:AAG1qZPHPqhUWdUhN0vHFItutpU2nhnLKvQ"
TELEGRAM_CHAT_ID = "7690013892"
