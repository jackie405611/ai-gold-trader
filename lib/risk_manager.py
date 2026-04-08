# ============================================================
#  lib/risk_manager.py  —  Risk Management (Vercel/Redis)
#  Adapted: MT5 account_info() → Redis snapshot, no threading
# ============================================================
from lib.config import (
    MAX_DD, RISK_PER_TRADE, USE_DYNAMIC_LOT,
    MAX_CONSECUTIVE_LOSS, MAX_DAILY_LOSS_PCT, TICK_VALUES,
)
import lib.state_store as store


def check_drawdown() -> bool:
    """
    Returns False (block trading) if any risk limit is breached.
    Reads account balance/equity from Redis snapshot.
    """
    snap  = store.get_account_snapshot()
    risk  = store.get_risk_state()

    bal   = snap.get("balance", 0)
    eq    = snap.get("equity", bal)

    if bal <= 0:
        return True  # no data yet, allow (fail-open at startup)

    dd = (bal - eq) / bal * 100 if bal > 0 else 0
    print(f"[Risk] DD:{dd:.2f}%  Balance:{bal:.2f}  Equity:{eq:.2f}")

    if dd >= MAX_DD:
        print("[Risk] ❌ MAX DD reached")
        store.disable_trading(reason="MAX DD reached", by="risk")
        return False

    daily_start = risk.get("daily_start_balance", 0) or bal
    daily_loss  = (daily_start - eq) / daily_start * 100 if daily_start > 0 else 0
    store.update_risk_state({"daily_loss_pct": daily_loss})

    if daily_loss >= MAX_DAILY_LOSS_PCT:
        print(f"[Risk] ❌ Daily loss {daily_loss:.2f}%")
        store.disable_trading(reason=f"Daily loss {daily_loss:.2f}%", by="risk")
        return False

    if risk.get("consecutive_losses", 0) >= MAX_CONSECUTIVE_LOSS:
        print(f"[Risk] ❌ {MAX_CONSECUTIVE_LOSS} consecutive losses")
        store.disable_trading(reason="Consecutive losses limit", by="risk")
        return False

    return True


def calculate_lot(atr: float, symbol: str, cfg: dict | None = None) -> float:
    """
    Dynamic lot calculation using TICK_VALUES (replaces mt5.symbol_info).
    """
    if not USE_DYNAMIC_LOT or not atr:
        return (cfg or {}).get("lot", 0.01)

    sl_mult    = (cfg or {}).get("atr_sl_mult", 1.5)
    snap       = store.get_account_snapshot()
    balance    = snap.get("balance", 0)

    if balance <= 0:
        return 0.01

    point      = TICK_VALUES.get(symbol, 0.01)        # USD per point per 0.01 lot
    sl_usd     = atr * sl_mult                        # SL distance in price units
    risk_usd   = balance * (RISK_PER_TRADE / 100)
    lot        = risk_usd / (sl_usd / point) if sl_usd > 0 else 0.01
    return max(0.01, min(round(lot, 2), 1.0))


def get_risk_summary() -> dict:
    snap = store.get_account_snapshot()
    risk = store.get_risk_state()

    bal  = snap.get("balance", 0)
    eq   = snap.get("equity", bal)
    dd   = (bal - eq) / bal * 100 if bal > 0 else 0

    return {
        "balance":        round(bal, 2),
        "equity":         round(eq,  2),
        "drawdown_pct":   round(dd,  2),
        "daily_loss_pct": round(risk.get("daily_loss_pct", 0), 2),
        "consec_losses":  risk.get("consecutive_losses", 0),
    }
