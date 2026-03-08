# ============================================================
#  chart_generator.py  —  Chart with RSI + EMA  (V3)
# ============================================================
import MetaTrader5 as mt5
import pandas as pd
import matplotlib
matplotlib.use('Agg')          # ← ใช้ non-GUI backend, ปลอดภัยสำหรับ thread ย่อย
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime


def generate_chart(symbol="XAUUSDm", timeframe=mt5.TIMEFRAME_M5,
                   candles=120, output="chart.png", signal_info=None):
    """
    สร้างกราฟ 2 panel:
      Top : Price + EMA9/21/50
      Bot : RSI(14) พร้อมเส้น 30/70
    signal_info : dict ที่ได้จาก ai_strategy (optional)
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, candles)
    if rates is None:
        print("[Chart] Cannot get rates")
        return None

    df            = pd.DataFrame(rates)
    df["time"]    = pd.to_datetime(df["time"], unit="s")
    df["ema9"]    = df["close"].ewm(span=9).mean()
    df["ema21"]   = df["close"].ewm(span=21).mean()
    df["ema50"]   = df["close"].ewm(span=50).mean()

    # RSI
    delta         = df["close"].diff()
    gain          = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss          = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    rs            = gain / loss.replace(0, 1e-10)
    df["rsi"]     = 100 - 100 / (1 + rs)

    fig = plt.figure(figsize=(12, 7), facecolor="#0d1117", constrained_layout=True)
    gs  = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.05, figure=fig)

    # ── Price Panel ──
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#0d1117")
    ax1.plot(df["time"], df["close"], color="#58a6ff", linewidth=1.2, label="Price")
    ax1.plot(df["time"], df["ema9"],  color="#f0883e", linewidth=1.0, label="EMA9")
    ax1.plot(df["time"], df["ema21"], color="#3fb950", linewidth=1.0, label="EMA21")
    ax1.plot(df["time"], df["ema50"], color="#bc8cff", linewidth=1.0, linestyle="--", label="EMA50")

    title = f"{symbol} M5"
    if signal_info:
        sig     = signal_info.get("m5_signal", "")
        regime  = signal_info.get("regime", "")
        adx     = signal_info.get("adx", "")
        title  += f"  |  Signal: {sig}  |  Regime: {regime}  |  ADX: {adx}"

    ax1.set_title(title, color="white", fontsize=10)
    ax1.tick_params(colors="gray", labelbottom=False)
    ax1.spines[:].set_color("#30363d")
    ax1.yaxis.label.set_color("white")
    ax1.legend(fontsize=8, facecolor="#161b22", labelcolor="white", loc="upper left")
    ax1.grid(color="#21262d", linestyle="--", linewidth=0.5)

    # ── RSI Panel ──
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor("#0d1117")
    ax2.plot(df["time"], df["rsi"], color="#79c0ff", linewidth=1.0)
    ax2.axhline(70, color="#f85149", linewidth=0.8, linestyle="--")
    ax2.axhline(30, color="#3fb950", linewidth=0.8, linestyle="--")
    ax2.axhline(50, color="#8b949e", linewidth=0.5, linestyle=":")
    ax2.fill_between(df["time"], df["rsi"], 70, where=(df["rsi"] >= 70), alpha=0.2, color="#f85149")
    ax2.fill_between(df["time"], df["rsi"], 30, where=(df["rsi"] <= 30), alpha=0.2, color="#3fb950")
    ax2.set_ylabel("RSI", color="gray", fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.tick_params(colors="gray", labelsize=7)
    ax2.spines[:].set_color("#30363d")
    ax2.grid(color="#21262d", linestyle="--", linewidth=0.5)

    plt.xticks(rotation=30, ha="right", color="gray", fontsize=7)
    fig.savefig(output, dpi=120, facecolor="#0d1117", bbox_inches="tight")
    plt.close(fig)

    print(f"[Chart] Saved → {output}")
    return output
