# ============================================================
#  get_data.py  —  Quick Test Script  (V2)
#  รันเพื่อทดสอบ signal โดยไม่เปิด trade จริง
# ============================================================
import MetaTrader5 as mt5
import pandas as pd
from mt5_connector import connect
from data_fetcher  import get_candles
from ai_strategy   import generate_signal, detect_regime
from ai_m5         import trend_signal, get_trend_strength
from ai_m1         import entry_signal

connect()

df_m5 = get_candles(mt5.TIMEFRAME_M5, count=200)
df_m1 = get_candles(mt5.TIMEFRAME_M1, count=200)

regime, adx, atr = detect_regime(df_m5)
print(f"Market Regime : {regime}")
print(f"ADX           : {adx:.2f}")
print(f"ATR (M5)      : {atr:.4f}")

m5 = trend_signal(df_m5)
m1_sig, m1_rsi, m1_atr = entry_signal(df_m1, m5_trend=m5)
print(f"\nM5 Trend      : {m5}")
print(f"M1 Entry      : {m1_sig}  (RSI={m1_rsi}, ATR={m1_atr})")

signal, info = generate_signal(df_m5, df_m1)
print(f"\n✅ Final Signal : {signal}")
print(f"Info           : {info}")

mt5.shutdown()
