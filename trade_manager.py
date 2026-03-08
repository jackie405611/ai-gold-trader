# ============================================================
#  trade_manager.py  —  Trade Execution V3 (per-symbol)
# ============================================================
import MetaTrader5 as mt5
from config import USE_TRAILING_STOP, TRAILING_ATR_MULT
from risk_manager import calculate_lot


def _norm(price, symbol):
    info = mt5.symbol_info(symbol)
    return round(price, info.digits) if info else round(price, 2)


def open_trade(symbol, cfg, signal, atr=None):
    if signal not in ("BUY", "SELL"):
        return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[Trade:{symbol}] ❌ No tick")
        return None

    lot = calculate_lot(atr, symbol, cfg)

    sl_mult = cfg.get("atr_sl_mult", 1.5)
    tp_mult = cfg.get("atr_tp_mult", 2.5)

    if signal == "BUY":
        price = tick.ask
        sl    = price - (atr or 1.0) * sl_mult
        tp    = price + (atr or 1.0) * tp_mult
        otype = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl    = price + (atr or 1.0) * sl_mult
        tp    = price - (atr or 1.0) * tp_mult
        otype = mt5.ORDER_TYPE_SELL

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         otype,
        "price":        _norm(price, symbol),
        "sl":           _norm(sl, symbol),
        "tp":           _norm(tp, symbol),
        "deviation":    20,
        "magic":        987654,
        "comment":      f"AI_V3 {signal}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[Trade:{symbol}] ✅ {signal} @ {price:.5f}  SL:{sl:.5f}  TP:{tp:.5f}")
    else:
        print(f"[Trade:{symbol}] ❌ Failed: {result}")
    return result


def update_trailing_stop(symbol, current_atr=None):
    if not USE_TRAILING_STOP:
        return
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return
    for pos in positions:
        dist = (current_atr or 1.0) * TRAILING_ATR_MULT
        new_sl = None
        if pos.type == mt5.ORDER_TYPE_BUY:
            candidate = tick.bid - dist
            if candidate > pos.sl + 0.0001:
                new_sl = _norm(candidate, symbol)
        elif pos.type == mt5.ORDER_TYPE_SELL:
            candidate = tick.ask + dist
            if candidate < pos.sl - 0.0001:
                new_sl = _norm(candidate, symbol)
        if new_sl:
            mt5.order_send({
                "action":   mt5.TRADE_ACTION_SLTP,
                "symbol":   symbol,
                "sl":       new_sl,
                "tp":       pos.tp,
                "position": pos.ticket,
            })
            print(f"[Trail:{symbol}] SL → {new_sl}")


def close_all_positions(symbol, comment="AI_close"):
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    tick = mt5.symbol_info_tick(symbol)
    for pos in positions:
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        otype = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
            "volume": pos.volume, "type": otype, "price": price,
            "deviation": 20, "magic": 987654, "comment": comment,
            "position": pos.ticket,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        print(f"[Trade:{symbol}] Closed #{pos.ticket}")
