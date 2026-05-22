"""EMA Ribbon Strategy backtester — historical signal replay with equity curve."""

import logging
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

from ema import EMA_PERIODS, TIMEFRAME_CONFIG, add_emas

logger = logging.getLogger(__name__)

VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
# Maximum lookback yfinance supports per interval
MAX_PERIOD = {"15m": "60d", "1h": "730d", "4h": "730d", "1d": "10y"}


def run_backtest(ticker: str, timeframe: str, period: str) -> None:
    if period not in VALID_PERIODS:
        print(f"Invalid period '{period}'. Choose from: {', '.join(sorted(VALID_PERIODS))}")
        return

    ticker = ticker.upper()
    cfg = TIMEFRAME_CONFIG[timeframe]

    print(f"\nFetching {ticker} ({timeframe}, {period})…")
    try:
        df = yf.Ticker(ticker).history(interval=cfg["interval"], period=period)
    except Exception as e:
        print(f"Data fetch error: {e}")
        return

    if df is None or df.empty:
        print(f"No data returned for {ticker}.")
        return

    if timeframe == "4h":
        df = (
            df.resample("4h")
            .agg({"Open": "first", "High": "max", "Low": "min",
                  "Close": "last", "Volume": "sum"})
            .dropna(subset=["Close"])
        )

    if len(df) < 10:
        print(f"Too few bars ({len(df)}) to backtest.")
        return

    df = add_emas(df)

    # Identify crossover bars
    close = df["Close"]
    h_ema = df["highest_ema"]
    above = close > h_ema

    signals: list[dict] = []
    for i in range(1, len(df)):
        c0, e0 = float(close.iloc[i]),     float(h_ema.iloc[i])
        c1, e1 = float(close.iloc[i - 1]), float(h_ema.iloc[i - 1])
        if c0 > e0 and c1 < e1:
            signals.append({"type": "BUY",  "date": df.index[i], "price": c0})
        elif c0 < e0 and c1 > e1:
            signals.append({"type": "SELL", "date": df.index[i], "price": c0})

    # Simulate long-only trades: BUY opens position, SELL closes it
    trades: list[dict] = []
    position: dict | None = None
    for sig in signals:
        if sig["type"] == "BUY" and position is None:
            position = {"entry_date": sig["date"], "entry_price": sig["price"]}
        elif sig["type"] == "SELL" and position is not None:
            gain_pct = (sig["price"] - position["entry_price"]) / position["entry_price"] * 100
            trades.append({
                "entry_date":  position["entry_date"],
                "exit_date":   sig["date"],
                "entry_price": position["entry_price"],
                "exit_price":  sig["price"],
                "gain_pct":    gain_pct,
                "win":         gain_pct > 0,
            })
            position = None

    # ── Summary stats ──────────────────────────────────────────────────────
    print(f"\n{'─' * 54}")
    print(f"  Backtest  {ticker}  |  {timeframe}  |  {period}")
    print(f"{'─' * 54}")
    print(f"  Total signals    : {len(signals)}")

    if not trades:
        print("  No completed trades found.")
        print(f"{'─' * 54}\n")
        return

    wins   = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    win_rate  = len(wins) / len(trades) * 100
    avg_gain  = sum(t["gain_pct"] for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss  = sum(t["gain_pct"] for t in losses) / len(losses) if losses else 0.0

    # Compound return (reinvest 100 % each trade)
    equity = 1.0
    eq_dates  = [trades[0]["entry_date"]]
    eq_values = [1.0]
    for t in trades:
        equity *= 1 + t["gain_pct"] / 100
        eq_dates.append(t["exit_date"])
        eq_values.append(equity)
    total_return = (equity - 1) * 100

    print(f"  Completed trades : {len(trades)}  ({len(wins)}W / {len(losses)}L)")
    print(f"  Win rate         : {win_rate:.1f}%")
    print(f"  Avg gain (W)     : +{avg_gain:.2f}%")
    print(f"  Avg loss (L)     :  {avg_loss:.2f}%")
    print(f"  Total return     : {total_return:+.2f}%")
    print(f"{'─' * 54}\n")

    _plot(ticker, timeframe, period, df, signals, eq_dates, eq_values)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _plot(ticker, timeframe, period, df, signals, eq_dates, eq_values):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=False)
    fig.patch.set_facecolor("#0d0d1a")
    fig.suptitle(
        f"{ticker}  EMA Ribbon Backtest  |  {timeframe}  |  {period}",
        fontsize=14, fontweight="bold", color="white",
    )

    # ── Price + EMA ribbon ──────────────────────────────────────────────────
    ax1.set_facecolor("#1a1a2e")
    ax1.plot(df.index, df["Close"], color="white", linewidth=1.1, label="Close", zorder=3)

    ribbon_colors = ["#ff6b6b", "#ffa07a", "#ffd700", "#90ee90", "#87ceeb", "#9370db"]
    for p, c in zip(EMA_PERIODS, ribbon_colors):
        ax1.plot(df.index, df[f"ema_{p}"], color=c, linewidth=0.7, alpha=0.75, label=f"EMA {p}")

    for sig in signals:
        if sig["type"] == "BUY":
            ax1.scatter(sig["date"], sig["price"], marker="^", color="lime",  s=55, zorder=5)
            ax1.axvline(sig["date"], color="lime", linewidth=0.6, alpha=0.35)
        else:
            ax1.scatter(sig["date"], sig["price"], marker="v", color="tomato", s=55, zorder=5)
            ax1.axvline(sig["date"], color="tomato", linewidth=0.6, alpha=0.35)

    ax1.set_ylabel("Price ($)", color="white")
    ax1.tick_params(colors="white")
    ax1.legend(loc="upper left", fontsize=7, ncol=4, facecolor="#1a1a2e", labelcolor="white")
    ax1.grid(True, alpha=0.15)
    for spine in ax1.spines.values():
        spine.set_edgecolor("#444")

    # ── Equity curve ────────────────────────────────────────────────────────
    ax2.set_facecolor("#1a1a2e")
    ax2.plot(eq_dates, eq_values, color="#00d4ff", linewidth=1.5)
    ax2.axhline(1.0, color="white", linewidth=0.8, linestyle="--", alpha=0.4)
    ax2.fill_between(eq_dates, 1.0, eq_values,
                     where=[v >= 1 for v in eq_values], color="green", alpha=0.18)
    ax2.fill_between(eq_dates, 1.0, eq_values,
                     where=[v < 1  for v in eq_values], color="red",   alpha=0.18)
    ax2.set_ylabel("Equity (×)", color="white")
    ax2.set_xlabel("Date", color="white")
    ax2.tick_params(colors="white")
    ax2.grid(True, alpha=0.15)
    for spine in ax2.spines.values():
        spine.set_edgecolor("#444")

    plt.tight_layout()

    out = f"backtest_{ticker}_{timeframe}_{period}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Equity curve saved → {out}")
    plt.show()
