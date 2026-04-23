# ============================================================
#  lib/chart_generator.py  —  Chart with EMA50/200 + RSI
#  Accepts pre-fetched DataFrame, returns PNG bytes.
# ============================================================
import io
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def generate_chart(df: pd.DataFrame, symbol: str = "XAUUSDm",
                   timeframe: str = "M15",
                   signal_info: dict | None = None) -> bytes | None:
    """
    2-panel chart: Price + EMA50/200, RSI panel.

    df          : OHLCV DataFrame with DatetimeIndex (from data_fetcher)
    symbol      : display name
    timeframe   : label shown in chart title (M15, H1, H4 etc.)
    signal_info : optional dict from ai_strategy — adds annotation to title
    Returns     : PNG bytes, or None if data is empty.
    """
    if df is None or df.empty:
        print("[Chart] No data")
        return None

    df = df.copy()
    df["ema21"]  = df["close"].ewm(span=21).mean()
    df["ema50"]  = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()

    delta      = df["close"].diff()
    gain       = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss       = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    df["rsi"]  = 100 - 100 / (1 + gain / loss.replace(0, 1e-10))

    fig = plt.figure(figsize=(12, 7), facecolor="#0d1117", constrained_layout=True)
    gs  = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.05, figure=fig)

    # ── Price Panel ──────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#0d1117")
    ax1.plot(df.index, df["close"],  color="#58a6ff", linewidth=1.2, label="Price")
    ax1.plot(df.index, df["ema21"],  color="#f0883e", linewidth=1.0, label="EMA21")
    ax1.plot(df.index, df["ema50"],  color="#3fb950", linewidth=1.0, label="EMA50")
    ax1.plot(df.index, df["ema200"], color="#bc8cff", linewidth=1.0,
             linestyle="--", label="EMA200")

    # Annotate signal type if provided
    title = f"{symbol}  {timeframe}"
    if signal_info:
        h4   = signal_info.get("h4_structure", "")
        etype = signal_info.get("entry_type", "")
        rr   = signal_info.get("rr", "")
        if h4 or etype:
            title += f"   |   H4: {h4}   Type: {etype}   R:R {rr}"

    ax1.set_title(title, color="white", fontsize=10)
    ax1.tick_params(colors="gray", labelbottom=False)
    ax1.spines[:].set_color("#30363d")
    ax1.yaxis.label.set_color("white")
    ax1.legend(fontsize=8, facecolor="#161b22", labelcolor="white", loc="upper left")
    ax1.grid(color="#21262d", linestyle="--", linewidth=0.5)

    # ── RSI Panel ────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor("#0d1117")
    ax2.plot(df.index, df["rsi"], color="#79c0ff", linewidth=1.0)
    ax2.axhline(70, color="#f85149", linewidth=0.8, linestyle="--")
    ax2.axhline(30, color="#3fb950", linewidth=0.8, linestyle="--")
    ax2.axhline(50, color="#8b949e", linewidth=0.5, linestyle=":")
    ax2.fill_between(df.index, df["rsi"], 70,
                     where=(df["rsi"] >= 70), alpha=0.2, color="#f85149")
    ax2.fill_between(df.index, df["rsi"], 30,
                     where=(df["rsi"] <= 30), alpha=0.2, color="#3fb950")
    ax2.set_ylabel("RSI", color="gray", fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.tick_params(colors="gray", labelsize=7)
    ax2.spines[:].set_color("#30363d")
    ax2.grid(color="#21262d", linestyle="--", linewidth=0.5)

    plt.xticks(rotation=30, ha="right", color="gray", fontsize=7)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, facecolor="#0d1117", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
