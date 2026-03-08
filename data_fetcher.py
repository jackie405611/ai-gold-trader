# ============================================================
#  data_fetcher.py  —  Market Data V3 (per-symbol)
# ============================================================
import MetaTrader5 as mt5
import pandas as pd


def get_candles(symbol, timeframe, count=500):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        print(f"[Data] ❌ Failed: {symbol} tf={timeframe}")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df


def get_latest_atr(symbol, timeframe=mt5.TIMEFRAME_M1, period=14):
    df = get_candles(symbol, timeframe, count=period + 50)
    if df is None:
        return 1.0
    h, l, c = df["high"], df["low"], df["close"]
    tr  = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return round(atr.iloc[-1], 4)
