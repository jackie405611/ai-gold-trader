from tradingview_ta import TA_Handler, Interval

def get_tv_data(symbol="XAUUSD", interval=Interval.INTERVAL_5_MINUTES):

    handler = TA_Handler(
        symbol=symbol,
        exchange="OANDA",
        screener="forex",
        interval=interval
    )

    analysis = handler.get_analysis()

    return {
        "recommendation": analysis.summary["RECOMMENDATION"],
        "rsi": analysis.indicators["RSI"],
        "ema20": analysis.indicators["EMA20"],
        "ema50": analysis.indicators["EMA50"],
        "close": analysis.indicators["close"]
    }
