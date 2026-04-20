# ============================================================
#  main.py  —  AI Multi-Symbol Trader V3
# ============================================================
import time
import traceback
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5
import bot_controller as ctrl

from mt5_connector import connect, disconnect, get_account_info
from data_fetcher import get_candles, get_latest_atr
from ai_strategy import generate_signal
from trade_manager import open_trade, update_trailing_stop, close_all_positions
from risk_manager import check_drawdown, record_trade_result, reset_daily, get_risk_summary
from filters import spread_ok, session_ok, position_exists, market_open
from telegram_bot import notify_bot_start, notify_trade_open, notify_risk_event, send_telegram, send_chart
from chart_generator import generate_chart
from config import LOOP_SECONDS, SYMBOLS
from command_listener import start_listener


_stats = {sym: {"trades": 0, "wins": 0, "losses": 0} for sym in SYMBOLS}
_last_reset_day = None


def _daily_reset():
    global _last_reset_day
    today = datetime.now(timezone.utc).date()
    if _last_reset_day != today:
        reset_daily()
        for sym in _stats:
            _stats[sym] = {"trades": 0, "wins": 0, "losses": 0}
        _last_reset_day = today
        print(f"[Main] 📅 New day: {today}")


def _check_closed(symbol, prev_count):
    current = mt5.positions_get(symbol=symbol) or []
    if len(current) < prev_count:
        deals = mt5.history_deals_get(
            datetime.now(timezone.utc) - timedelta(hours=1),
            datetime.now(timezone.utc),
        )
        if deals:
            last = deals[-1]
            profit = last.profit
            record_trade_result(profit)

            if profit > 0:
                _stats[symbol]["wins"] += 1
            else:
                _stats[symbol]["losses"] += 1

            send_telegram(
                f"{'✅ WIN' if profit > 0 else '❌ LOSS'} "
                f"<b>{symbol}</b> <code>{profit:+.2f} USD</code>"
            )
    return len(current)


def _process_symbol(symbol, cfg, prev_counts):
    atr_live = get_latest_atr(symbol, mt5.TIMEFRAME_M1)
    update_trailing_stop(symbol, atr_live)

    prev_counts[symbol] = _check_closed(symbol, prev_counts.get(symbol, 0))

    if not spread_ok(symbol, cfg):
        return
    if not session_ok(cfg):
        return
    if position_exists(symbol):
        return

    df_h1 = get_candles(symbol, mt5.TIMEFRAME_H1)
    df_m15 = get_candles(symbol, mt5.TIMEFRAME_M15)
    df_m5 = get_candles(symbol, mt5.TIMEFRAME_M5)
    df_m1 = get_candles(symbol, mt5.TIMEFRAME_M1)

    if any(x is None for x in [df_h1, df_m15, df_m5, df_m1]):
        print(f"[{symbol}] candle data unavailable")
        return

    strategy_mode = ctrl.get_strategy_mode(symbol)

    final_signal, info = generate_signal(
        df_h1=df_h1,
        df_m15=df_m15,
        df_m5=df_m5,
        df_m1=df_m1,
        cfg=cfg,
        mode=strategy_mode,
    )

    print(
        f"[{symbol}] signal={final_signal} "
        f"mode={strategy_mode} "
        f"strategy={info.get('strategy', '-')} "
        f"regime={info.get('regime', '-')} "
        f"bias={info.get('bias', '-')} "
        f"reason={info.get('reason', '-')}"
    )

    if final_signal not in ("BUY", "SELL"):
        return

    entry = info.get("entry")
    sl = info.get("sl")
    tp = info.get("tp")

    if entry is None or sl is None or tp is None:
        print(f"[{symbol}] missing trade plan")
        return

    if not ctrl.should_trade(symbol):
        send_telegram(
            f"📣 <b>{symbol}</b> {final_signal}\n"
            f"mode=<code>{strategy_mode}</code>\n"
            f"strategy=<code>{info.get('strategy')}</code>\n"
            f"entry=<code>{entry}</code>\n"
            f"sl=<code>{sl}</code>\n"
            f"tp=<code>{tp}</code>\n"
            f"reason=<code>{info.get('reason')}</code>"
        )
        return

    result = open_trade(symbol, final_signal, sl, tp, cfg)
    if result:
        _stats[symbol]["trades"] += 1
        notify_trade_open(
            symbol=symbol,
            side=final_signal,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=(
                f"mode={strategy_mode} "
                f"strategy={info.get('strategy')} "
                f"bias={info.get('bias')} "
                f"rr={info.get('rr')}"
            ),
        )


def main():
    connect()
    print(f"[Main] Account: {get_account_info()}")
    print(f"[Main] Symbols: {list(SYMBOLS.keys())}")

    start_listener()
    notify_bot_start("V3")

    for sym, cfg in SYMBOLS.items():
        chart = generate_chart(symbol=sym)
        if chart:
            send_chart(chart, f"🤖 AI Trader V3 — {cfg['label']}")

    prev_counts = {sym: 0 for sym in SYMBOLS}
    loop_count = 0

    while ctrl.is_bot_running():
        try:
            loop_count += 1
            _daily_reset()
            now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            auto = "✅" if ctrl.is_trading_enabled() else "⏸"
            print(f"\n{'=' * 55}")
            print(f"[Main] Loop #{loop_count} | {now} | Auto:{auto}")

            if not check_drawdown():
                notify_risk_event("MAX DRAWDOWN — Auto trade disabled")
                for sym in SYMBOLS:
                    close_all_positions(sym, "max_dd")
                ctrl.disable_trading(reason="Max DD", by="risk")

            if not market_open():
                print("[Main] Market closed — sleep 15 min")
                time.sleep(900)
                continue

            for symbol, cfg in SYMBOLS.items():
                try:
                    _process_symbol(symbol, cfg, prev_counts)
                except Exception as e:
                    print(f"[Main:{symbol}] ⚠️ {e}")

            if loop_count % 30 == 0:
                rs = get_risk_summary()
                lines = [
                    "📊 <b>Status Update</b>",
                    f"Balance: <code>{rs.get('balance','?')}</code>  DD: <code>{rs.get('drawdown_pct','?')}%</code>",
                    "",
                ]
                for sym, cfg in SYMBOLS.items():
                    s = _stats[sym]
                    state = "✅" if ctrl.should_trade(sym) else "⏸"
                    lines.append(f"{state} <b>{cfg['label']}</b> T:{s['trades']} W:{s['wins']} L:{s['losses']}")
                send_telegram("\n".join(lines))

        except KeyboardInterrupt:
            print("\n[Main] Ctrl+C")
            send_telegram("🛑 Bot stopped (Ctrl+C)", blocking=True)
            break

        except Exception as e:
            print(f"[Main] ⚠️ {e}\n{traceback.format_exc()}")
            send_telegram(f"⚠️ Error: {str(e)[:200]}")
            time.sleep(LOOP_SECONDS * 2)

        time.sleep(LOOP_SECONDS)

    send_telegram("🛑 <b>Bot shut down</b>", blocking=True)
    disconnect()
    print("[Main] Bye!")


if __name__ == "__main__":
    main()
