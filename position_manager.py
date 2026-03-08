# ============================================================
#  position_manager.py  —  Position Tracker  (V2)
# ============================================================
import MetaTrader5 as mt5
from config import SYMBOL


def has_open_position():
    positions = mt5.positions_get(symbol=SYMBOL)
    return bool(positions)


def get_open_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []
    return [
        {
            "ticket":  p.ticket,
            "type":    "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume":  p.volume,
            "open_price": p.price_open,
            "sl":      p.sl,
            "tp":      p.tp,
            "profit":  p.profit,
            "comment": p.comment,
        }
        for p in positions
    ]


def get_total_profit():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return 0.0
    return sum(p.profit for p in positions)
