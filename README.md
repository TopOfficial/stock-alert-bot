# Stock Price Alert Bot

Monitors stocks and sends notifications to your **macOS desktop** and **LINE** when alerts trigger.

Two alert modes:
- **Price Target** — notify when a stock crosses a fixed price level
- **EMA Ribbon** — notify on a crossover signal using 6 EMAs (5, 12, 34, 55, 100, 200)

---

## Setup

```bash
cd stock-alert-bot

# Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
```

Edit `.env` and fill in your LINE credentials (see LINE setup below). The bot works without LINE — it will still send macOS desktop notifications.

---

## LINE Setup

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Create a **Messaging API** channel (Provider → Create a channel → Messaging API)
3. In the channel settings:
   - Copy the **Channel access token** (long-lived) → `LINE_CHANNEL_ACCESS_TOKEN`
4. Get your **LINE User ID**:
   - In the channel's Messaging API tab, look for "Your user ID" → `LINE_USER_ID`
   - Or use the LINE Official Account Manager webhook and log the `source.userId` from an incoming event
5. Paste both values into your `.env` file
6. Test the connection:
   ```bash
   python bot.py test-line
   ```

---

## Commands

### Price-target alerts

```bash
# Add (or update) a price alert
python bot.py add <TICKER> <PRICE> <above|below>

# Examples
python bot.py add AAPL 200 above    # alert when AAPL rises above $200
python bot.py add TSLA 180 below    # alert when TSLA drops below $180

# Remove an alert
python bot.py remove AAPL
```

### EMA Ribbon watchlist

```bash
# Add a ticker to the EMA watchlist
python bot.py watch <TICKER> <TIMEFRAME>
# TIMEFRAME: 15m | 1h | 4h | 1d

# Examples
python bot.py watch AAPL 1d       # daily EMA signals on Apple
python bot.py watch BTC-USD 1h    # hourly signals on Bitcoin
python bot.py watch SPY 15m       # 15-minute signals on S&P 500 ETF

# Remove from EMA watchlist
python bot.py unwatch AAPL
```

### View both watchlists

```bash
python bot.py list
```

Output example:
```
=== Price Alerts ===
Ticker       Target Direction     Current  Status
──────────────────────────────────────────────────────
TSLA     $  180.00 below         $183.10  Watching
AAPL     $  200.00 above         $194.30  Watching

=== EMA Watchlist ===
Ticker   Timeframe  Last Signal  Last Signal Bar
───────────────────────────────────────────────────────
SPY      1d         BUY          2026-05-20T00:00
AAPL     1h         —            —
```

### Start continuous monitoring

```bash
python bot.py run
```

Check schedule:

| Watchlist type | Timeframe | Check frequency               |
|----------------|-----------|-------------------------------|
| Price alerts   | —         | Every 5 minutes               |
| EMA ribbon     | 15m       | Every 15 minutes              |
| EMA ribbon     | 1h        | Every hour                    |
| EMA ribbon     | 4h        | Every 4 hours                 |
| EMA ribbon     | 1d        | Daily at 16:05 New York time  |

Press **Ctrl+C** to stop.

### Backtest the EMA strategy

```bash
python bot.py backtest <TICKER> <TIMEFRAME> <PERIOD>
# PERIOD: 1mo | 3mo | 6mo | 1y | 2y | 5y
```

Examples:
```bash
python bot.py backtest AAPL 1d 2y
python bot.py backtest SPY 1h 6mo
python bot.py backtest BTC-USD 4h 1y
```

Output:
```
──────────────────────────────────────────────────────
  Backtest  AAPL  |  1d  |  1y
──────────────────────────────────────────────────────
  Total signals    : 41
  Completed trades : 20  (7W / 13L)
  Win rate         : 35.0%
  Avg gain (W)     : +3.83%
  Avg loss (L)     :  -1.01%
  Total return     : +13.63%
──────────────────────────────────────────────────────
Equity curve saved → backtest_AAPL_1d_1y.png
```

An equity-curve chart is saved as a PNG and opened automatically.

> **yfinance data limits:** 15m → 60 days, 1h / 4h → 730 days, 1d → up to 10 years.

### Test LINE connection

```bash
python bot.py test-line
```

### Send test BUY + SELL signals

```bash
python bot.py test-signal <TICKER>
```

Fetches real price and EMA data for the ticker, then sends **two messages** to LINE — one fake BUY and one fake SELL — so you can confirm the formatting before relying on live signals. Messages are prefixed with `[TEST]` so they can't be confused with real alerts.

If the ticker is already in your EMA watchlist its configured timeframe is used; otherwise defaults to `1d`.

Example:
```bash
python bot.py test-signal AAPL
```

Terminal output:
```
Fetching AAPL (1d) for test signals…

Data  →  AAPL  |  Price: $310.36  |  Highest EMA: $304.22  |  TF: 1d

── BUY preview ──
[TEST]
🟢 BUY SIGNAL
Ticker: AAPL
Price: $310.36
Timeframe: 1d
Highest EMA: $304.22
Time: 2026-05-22 21:45 (Bangkok time)

── SELL preview ──
[TEST]
🔴 SELL SIGNAL
...

Sending [TEST] BUY to LINE…
Sending [TEST] SELL to LINE…
✓ Both test signals sent! Check your LINE app.
```

### EMA Ribbon Report

```bash
python bot.py report
```

Fetches live data for **every ticker in the EMA watchlist**, calculates how far the current price sits above or below the highest EMA, then sends a ranked snapshot to LINE (and prints it to the terminal).

**Sort order:**
1. 🟢 ABOVE — bullish stocks, sorted by largest % gap first
2. 🔴 BELOW — bearish stocks, sorted by closest to the crossover line first

Example LINE message:
```
📊 EMA Ribbon Report
2026-05-22 18:30 (Bangkok)
─────────────────
🟢 AAPL (1d)
Price: $310.36
Highest EMA: $304.22
Diff: +2.02% ABOVE
─────────────────
🔴 TSLA (1d)
Price: $180.50
Highest EMA: $185.20
Diff: -2.54% BELOW
─────────────────
```

If a ticker's data can't be fetched it is skipped gracefully; the rest of the report still sends.

---

## EMA Ribbon Strategy

Translated from Pine Script:

```
EMAs calculated: 5, 12, 34, 55, 100, 200 periods
highest_ema = max(ema5, ema12, ema34, ema55, ema100, ema200)

BUY  signal: close crosses ABOVE highest_ema
             (previous bar: close < highest_ema  →  current bar: close > highest_ema)

SELL signal: close crosses BELOW highest_ema
             (previous bar: close > highest_ema  →  current bar: close < highest_ema)
```

**Duplicate prevention:** each alert is tagged with the bar's timestamp. The same bar can only trigger one notification, even if the bot checks multiple times before the next bar closes.

**Alert reset:** if the price retreats back past the target (price-target mode), the alert resets so it can fire again on the next breach.

---

## Alert format

```
🟢 BUY SIGNAL
Ticker: AAPL
Price: $150.23
Timeframe: 1d
Highest EMA: $148.50
Time: 2026-05-22 15:30 (Bangkok time)
```

SELL alerts use 🔴. Price-target alerts use 📈/📉.

---

## File structure

```
stock-alert-bot/
├── bot.py            # CLI entry point + scheduler
├── ema.py            # EMA calculations + signal detection
├── notifier.py       # macOS desktop + LINE notifications
├── backtest.py       # Historical strategy backtesting + chart
├── storage.py        # watchlist.json read/write
├── requirements.txt
├── .env.example      # Credential template — copy to .env
├── .env              # Your credentials (never commit this)
├── watchlist.json    # Auto-created persistence file
├── bot.log           # Auto-created log file
└── README.md
```

---

## Logging

All events are written to `bot.log` (INFO level). The terminal shows a clean status-line view. To follow logs live:

```bash
tail -f bot.log
```

---

## Extending notifications

The `notifier.alert()` function in `notifier.py` sends to both desktop and LINE. To add Telegram:

```python
import requests

def send_telegram(text: str) -> bool:
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    return resp.ok
```

Then call `send_telegram(message)` inside `alert()`.
