# ============================================================
#  main.py  —  AI Multi-Symbol Trader V3
#  วน loop ทุก symbol ใน config.SYMBOLS ในรอบเดียวกัน
# ============================================================
import time, traceback
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

from mt5_connector    import connect, disconnect, get_account_info
from data_fetcher     import get_candles, get_latest_atr
from ai_m5            import trend_signal
from ai_m1            import entry_signal
from ai_strategy      import generate_signal, detect_regime
from trade_manager    import open_trade, update_trailing_stop, close_all_positions
from risk_manager     import check_drawdown, record_trade_result, reset_daily, get_risk_summary
from filters          import spread_ok, session_ok, position_exists, market_open
from telegram_bot     import (notify_bot_start, notify_trade_open,
                               notify_risk_event, send_telegram, send_chart)
from chart_generator  import generate_chart
from config           import LOOP_SECONDS, SYMBOLS
import bot_controller as ctrl
from command_listener import start_listener


# ── สถิติรอบวัน ──────────────────────────────────────────────
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
    """ตรวจ position ที่เพิ่งปิด"""
    current = mt5.positions_get(symbol=symbol) or []
    if len(current) < prev_count:
        deals = mt5.history_deals_get(
            datetime.now(timezone.utc) - timedelta(hours=1),
            datetime.now(timezone.utc)
        )
        if deals:
            last   = deals[-1]
            profit = last.profit
            record_trade_result(profit)
            if profit > 0: _stats[symbol]["wins"]   += 1
            else:          _stats[symbol]["losses"] += 1
            send_telegram(
                f"{'✅ WIN' if profit > 0 else '❌ LOSS'}  "
                f"<b>{symbol}</b>  <code>{profit:+.2f} USD</code>"
            )
    return len(current)


def _process_symbol(symbol, cfg, prev_counts):
    """วิเคราะห์และ execute สำหรับ 1 symbol"""

    # Trailing stop ทุก loop
    atr_live = get_latest_atr(symbol, mt5.TIMEFRAME_M1)
    update_trailing_stop(symbol, atr_live)

    # ตรวจ closed positions
    prev_counts[symbol] = _check_closed(symbol, prev_counts.get(symbol, 0))

    # ── Filters ──
    if not spread_ok(symbol, cfg):    return
    if not session_ok(cfg):           return
    if position_exists(symbol):       return

    # ── Data ──
    df_m5 = get_candles(symbol, mt5.TIMEFRAME_M5)
    df_m1 = get_candles(symbol, mt5.TIMEFRAME_M1)
    if df_m5 is None or df_m1 is None:
        return

    # ── AI (วิเคราะห์เสมอ ไม่ว่าสวิตช์จะเปิดหรือปิด) ──
    final_signal, info = generate_signal(df_m5, df_m1, cfg=cfg)
    regime = info.get("regime", "?")
    adx    = info.get("adx", 0)
    atr    = info.get("atr", atr_live)
    label  = cfg.get("label", symbol)

    print(f"[{symbol}] {final_signal}  Regime:{regime}  ADX:{adx}  ATR:{atr}")

    if final_signal not in ("BUY", "SELL"):
        return

    # ── คำนวณ entry/SL/TP ──
    tick  = mt5.symbol_info_tick(symbol)
    price = tick.ask if final_signal == "BUY" else tick.bid
    sl_m  = cfg.get("atr_sl_mult", 1.5)
    tp_m  = cfg.get("atr_tp_mult", 2.5)
    sl    = price - atr*sl_m if final_signal == "BUY" else price + atr*sl_m
    tp    = price + atr*tp_m if final_signal == "BUY" else price - atr*tp_m
    rr    = round(abs(tp - price) / max(abs(sl - price), 0.0001), 2)

    if ctrl.should_trade(symbol):
        # ── AUTO MODE ──
        result = open_trade(symbol, cfg, final_signal, atr)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            _stats[symbol]["trades"] += 1
            prev_counts[symbol] = prev_counts.get(symbol, 0) + 1
            notify_trade_open(
                signal=final_signal, price=round(price,2),
                sl=round(sl,2), tp=round(tp,2),
                lot=getattr(result, "volume", "?"),
                atr=atr, regime=f"{regime} | {label}",
            )
            chart = generate_chart(symbol=symbol, signal_info=info)
            if chart: send_chart(chart, f"📊 {label} Auto: {final_signal}")
    else:
        # ── ALERT ONLY MODE ──
        emoji = "🟢" if final_signal == "BUY" else "🔴"
        send_telegram(
            f"{emoji} <b>SIGNAL — {final_signal} {label}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ <i>Manual Mode</i>\n"
            f"💰 Entry : <code>{price:.5f}</code>\n"
            f"🛡  SL    : <code>{sl:.5f}</code>\n"
            f"🎯 TP    : <code>{tp:.5f}</code>\n"
            f"📈 RR    : <code>1:{rr}</code>\n"
            f"🌐 Regime: <code>{regime}</code>  ADX:<code>{adx}</code>\n"
            f"💡 /enable {symbol}  เพื่อเปิด auto trade"
        )
        chart = generate_chart(symbol=symbol, signal_info=info)
        if chart: send_chart(chart, f"📊 {label} Alert: {final_signal}")


# ── Main ─────────────────────────────────────────────────────

def main():
    connect()
    print(f"[Main] Account: {get_account_info()}")
    print(f"[Main] Symbols: {list(SYMBOLS.keys())}")

    start_listener()
    notify_bot_start("V3")

    # ส่ง chart เริ่มต้นทุก symbol
    for sym, cfg in SYMBOLS.items():
        chart = generate_chart(symbol=sym)
        if chart:
            send_chart(chart, f"🤖 AI Trader V3 — {cfg['label']}")

    prev_counts = {sym: 0 for sym in SYMBOLS}
    loop_count  = 0

    while ctrl.is_bot_running():
        try:
            loop_count += 1
            _daily_reset()
            now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            auto = "✅" if ctrl.is_trading_enabled() else "⏸"
            print(f"\n{'='*55}")
            print(f"[Main] Loop #{loop_count} | {now} | Auto:{auto}")

            # ── Global Risk Gate ──
            if not check_drawdown():
                notify_risk_event("MAX DRAWDOWN — Auto trade disabled")
                for sym in SYMBOLS:
                    close_all_positions(sym, "max_dd")
                ctrl.disable_trading(reason="Max DD", by="risk")

            if not market_open():
                print("[Main] Market closed — sleep 15 min")
                time.sleep(900)
                continue

            # ── วน loop ทุก symbol ──
            for symbol, cfg in SYMBOLS.items():
                try:
                    _process_symbol(symbol, cfg, prev_counts)
                except Exception as e:
                    print(f"[Main:{symbol}] ⚠️ {e}")

            # ── Summary ทุก 30 loop ──
            if loop_count % 30 == 0:
                rs    = get_risk_summary()
                lines = [
                    f"📊 <b>Status Update</b>",
                    f"Balance: <code>{rs.get('balance','?')}</code>  DD: <code>{rs.get('drawdown_pct','?')}%</code>",
                    "",
                ]
                for sym, cfg in SYMBOLS.items():
                    s     = _stats[sym]
                    state = "✅" if ctrl.should_trade(sym) else "⏸"
                    lines.append(f"{state} <b>{cfg['label']}</b>  T:{s['trades']} W:{s['wins']} L:{s['losses']}")
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
