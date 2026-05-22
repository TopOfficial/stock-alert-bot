# 📈 Stock Alert Bot

A Python terminal bot that monitors stocks and fires real-time alerts to **LINE** and macOS desktop when price targets or EMA crossover signals are hit.

---

## Demo

| LINE Report | Backtest Equity Curve |
|:-----------:|:---------------------:|
| ![LINE Report](docs/line_report.png) | ![Backtest](docs/backtest_curve.png) |

---

## Features

- **EMA Ribbon Strategy** — six-EMA crossover system (5, 12, 34, 55, 100, 200) translated directly from Pine Script
- **Price Target Alerts** — fire once when a stock crosses a fixed price level; auto-resets when price retreats
- **LINE Messaging API** — push alerts straight to your LINE chat; falls back to macOS desktop notifications
- **Multi-timeframe support** — 15 m, 1 h, 4 h, 1 d on any ticker yfinance supports (stocks, ETFs, crypto)
- **`/report` command** — instant snapshot of every watched ticker ranked by distance from the EMA ribbon
- **Backtesting** — replay the strategy on historical data with a dark-theme equity curve chart exported as PNG
- **Persistent watchlist** — JSON file survives restarts; both price-target and EMA watches in one place
- **Structured logging** — all events go to `bot.log`; terminal stays clean

---

## Strategy

The **EMA Ribbon** groups six exponential moving averages into a single dynamic support/resistance zone. The key insight is finding the **highest** of all six EMAs at each bar — this becomes the "ceiling" in a downtrend and "floor" in an uptrend.

```
Ribbon EMAs: 5 · 12 · 34 · 55 · 100 · 200 periods
Highest EMA = max(ema5, ema12, ema34, ema55, ema100, ema200)

🟢 BUY  — close crosses ABOVE highest EMA (first bar of the cross only)
🔴 SELL — close crosses BELOW highest EMA (first bar of the cross only)
```

Signals fire **only on the opening bar of a cross** — exactly matching Pine Script's `ta.crossover` / `ta.crossunder` semantics. Once a signal is sent, it is suppressed until the next genuine cross to prevent duplicate alerts.

---

## Installation

```bash
# 1 — Clone
git clone https://github.com/your-username/stock-alert-bot.git
cd stock-alert-bot

# 2 — Virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3 — Dependencies
pip install -r requirements.txt

# 4 — Credentials
cp .env.example .env
# Edit .env and fill in LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID
```

### LINE setup

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Create a **Messaging API** channel
3. Copy the **Channel access token** (long-lived) → `LINE_CHANNEL_ACCESS_TOKEN`
4. Find your user ID in the Messaging API tab → `LINE_USER_ID`
5. Verify the connection:

```bash
python bot.py test-line
```

The bot works without LINE — all alerts also appear as macOS desktop notifications.

---

## Usage

### Price target alerts

```bash
# Alert when AAPL rises above $200
python bot.py add AAPL 200 above

# Alert when TSLA drops below $180
python bot.py add TSLA 180 below

# Remove alert
python bot.py remove AAPL
```

### EMA ribbon watchlist

```bash
# Watch AAPL on the daily timeframe
python bot.py watch AAPL 1d

# Timeframe options: 15m | 1h | 4h | 1d
python bot.py watch BTC-USD 1h
python bot.py watch SPY 15m

# Remove
python bot.py unwatch AAPL
```

### View all active alerts

```bash
python bot.py list
```

```
=== Price Alerts ===
Ticker       Target Direction     Current  Status
──────────────────────────────────────────────────────
TSLA     $  180.00 below         $183.10  Watching

=== EMA Watchlist ===
Ticker   Timeframe  Last Signal  Last Signal Bar
───────────────────────────────────────────────────────
AAPL     1d         BUY          2026-05-20T00:00
SPY      1h         —            —
```

### Live monitoring

```bash
python bot.py run
```

| Check type | Frequency |
|---|---|
| Price alerts | Every 5 minutes |
| EMA 15 m | Every 15 minutes |
| EMA 1 h | Every hour |
| EMA 4 h | Every 4 hours |
| EMA 1 d | Daily at 16:05 New York time (after NYSE close) |

### EMA status report → LINE

```bash
python bot.py report
```

Sends a ranked snapshot of the entire EMA watchlist to LINE. Sorted by **distance from the ribbon**: most bullish (largest % above) at the top; most at-risk bearish stocks (closest to crossing) just below the divider.

```
📊 EMA Ribbon Report
2026-05-22 18:30 (Bangkok)
─────────────────
🟢 IONQ (1d)
Price: $65.36
Highest EMA: $57.78
Diff: +13.13% ABOVE
─────────────────
🔴 NAMS (1d)
Price: $35.25
Highest EMA: $35.38
Diff: -0.36% BELOW
─────────────────
```

### Backtest

```bash
python bot.py backtest <TICKER> <TIMEFRAME> <PERIOD>
# PERIOD: 1mo | 3mo | 6mo | 1y | 2y | 5y
```

```bash
python bot.py backtest AAPL 1d 2y
python bot.py backtest SPY  1h 6mo
python bot.py backtest BTC-USD 4h 1y
```

### Test LINE formatting

```bash
# Send a connection test
python bot.py test-line

# Send a fake BUY + SELL alert using real data (labelled [TEST])
python bot.py test-signal AAPL
```

---

## Backtest Results

Example run — **AAPL daily, 2-year lookback:**

| Metric | Value |
|---|---|
| Total signals | 74 |
| Completed trades | 37 |
| Win rate | 39.4% |
| Avg gain (winners) | +4.1% |
| Avg loss (losers) | −1.6% |
| Reward / Risk ratio | 2.6× |
| **Total return** | **+19.5%** |

> Results are from a long-only simulation (buy on BUY signal, close on SELL signal). Past performance is not indicative of future results.

---

## Tech Stack

| Layer | Library |
|---|---|
| Data | [yfinance](https://github.com/ranaroussi/yfinance) |
| Indicators | [pandas](https://pandas.pydata.org/) `.ewm()` |
| Notifications | [LINE Messaging API](https://developers.line.biz/en/docs/messaging-api/) · macOS `osascript` |
| Scheduling | [schedule](https://schedule.readthedocs.io/) |
| Charts | [matplotlib](https://matplotlib.org/) |
| Config | [python-dotenv](https://github.com/theskumar/python-dotenv) |

---

## Project Structure

```
stock-alert-bot/
├── bot.py            # CLI entry point + scheduler
├── ema.py            # EMA calculations + signal detection
├── notifier.py       # macOS desktop + LINE notifications
├── backtest.py       # Historical strategy replay + chart export
├── storage.py        # watchlist.json persistence + migration
├── requirements.txt
├── .env.example      # Credential template
├── .env              # Your credentials — never commit this
├── watchlist.json    # Auto-created
├── bot.log           # Auto-created
└── docs/
    ├── line_report.png
    └── backtest_curve.png
```

---

## Future Improvements

- [ ] **Multi-asset portfolio tracking** — aggregate P&L and exposure across all positions
- [ ] **Position sizing** — Kelly criterion or fixed-fractional sizing built into signals
- [ ] **Telegram support** — drop-in alternative to LINE using the Bot API
- [ ] **Additional strategies** — RSI divergence, MACD crossover, Bollinger Band squeeze
- [ ] **Web dashboard** — Flask/FastAPI frontend to manage the watchlist without the CLI
- [ ] **Cloud deployment** — run 24/7 on a Raspberry Pi or a small VPS with systemd

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

> **Note:** Screenshots go in the `docs/` folder. Add `docs/line_report.png` (a screenshot of a LINE report message) and `docs/backtest_curve.png` (a backtest chart PNG, one is already generated after running `python bot.py backtest AAPL 1d 1y`) to complete the Demo section.
