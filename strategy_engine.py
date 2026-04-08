from tradingview_ta import Interval
from data_fetcher import get_tv_data

def analyze_market():

    m1 = get_tv_data(interval=Interval.INTERVAL_1_MINUTE)
    m5 = get_tv_data(interval=Interval.INTERVAL_5_MINUTES)
    m15 = get_tv_data(interval=Interval.INTERVAL_15_MINUTES)

    buy_score = 0
    sell_score = 0

    for tf in [m1, m5, m15]:

        if tf["recommendation"] == "BUY":
            buy_score += 1

        if tf["recommendation"] == "SELL":
            sell_score += 1

    if buy_score >= 2:
        return "BUY", m5["close"]

    if sell_score >= 2:
        return "SELL", m5["close"]

    return "NEUTRAL", m5["close"]
