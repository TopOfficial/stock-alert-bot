#!/usr/bin/env python3
"""
Stock Price Alert Bot — CLI entry point.

Commands:
  add <TICKER> <PRICE> <above|below>      Price-target alert
  remove <TICKER>                          Remove price alert
  watch <TICKER> <TIMEFRAME>              EMA-ribbon watchlist
  unwatch <TICKER>                         Remove from EMA watchlist
  list                                     Show both watchlists (live prices)
  run                                      Start continuous monitoring
  backtest <TICKER> <TIMEFRAME> <PERIOD>  Historical EMA strategy test
  test-line                                Send a LINE test message
"""

import sys
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf
import schedule

import storage
import ema as ema_mod
import notifier
import backtest as backtest_mod

# ---------------------------------------------------------------------------
# Logging — INFO+ to bot.log; WARNING+ to console via print() calls
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8")],
)
logger = logging.getLogger(__name__)

BKK = ZoneInfo("Asia/Bangkok")
PRICE_CHECK_MINUTES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_bkk() -> str:
    return datetime.now(BKK).strftime("%H:%M:%S")


def get_price(ticker: str) -> float | None:
    """Fetch the latest traded price for ticker, or None on failure."""
    try:
        price = yf.Ticker(ticker).fast_info.last_price
        return round(float(price), 2) if price is not None else None
    except Exception as e:
        logger.warning("Price fetch failed for %s: %s", ticker, e)
        print(f"  Warning: could not fetch {ticker} — {e}")
        return None


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

def check_price_alerts() -> None:
    """Check every price-target alert and send notifications where targets are met."""
    data = storage.load()
    alerts = data["price_alerts"]

    if not alerts:
        return

    print(f"[{_now_bkk()}] Price-alert check ({len(alerts)} ticker(s))…")
    logger.info("Price-alert check started (%d tickers)", len(alerts))

    changed = False
    for ticker, cfg in alerts.items():
        current = get_price(ticker)
        if current is None:
            continue

        target    = cfg["target_price"]
        direction = cfg["direction"]
        alerted   = cfg.get("alerted", False)
        hit = (direction == "above" and current >= target) or \
              (direction == "below" and current <= target)

        if hit and not alerted:
            msg = notifier.format_price_alert(ticker, current, target, direction)
            print(f"  🔔 ALERT: {ticker} ${current:.2f} → target {direction} ${target:.2f}")
            logger.info("Price alert fired: %s %s $%.2f (target %s $%.2f)",
                        ticker, direction, current, direction, target)
            notifier.alert(f"{'📈' if direction == 'above' else '📉'} Price Alert — {ticker}", msg)
            alerts[ticker]["alerted"] = True
            changed = True

        elif not hit and alerted:
            # Price retreated past target — reset so it can fire again on next breach
            alerts[ticker]["alerted"] = False
            changed = True
            arrow = "▲" if direction == "above" else "▼"
            print(f"  {ticker}: ${current:.2f}  (alert reset, watching {arrow} ${target:.2f})")

        else:
            arrow = "▲" if direction == "above" else "▼"
            print(f"  {ticker}: ${current:.2f}  (watching {arrow} ${target:.2f})")

    if changed:
        storage.save(data)


def check_ema_watchlist(timeframe: str) -> None:
    """
    Run EMA ribbon signal detection for all tickers on the given timeframe.
    Deduplicates alerts by comparing bar timestamps — only fires once per bar.
    Skips weekends (no new bars, no new signals).
    """
    # Weekend guard — US markets closed Sat/Sun; no new bars will form
    if datetime.now(BKK).weekday() >= 5 and timeframe != "1d":
        logger.debug("Skipping EMA check (%s) — weekend", timeframe)
        return

    data = storage.load()
    ema_watch = data["ema_watchlist"]
    tickers = [t for t, d in ema_watch.items() if d["timeframe"] == timeframe]

    if not tickers:
        return

    print(f"[{_now_bkk()}] EMA check ({timeframe}): {', '.join(tickers)}")
    logger.info("EMA check (%s): %s", timeframe, tickers)

    changed = False
    for ticker in tickers:
        time.sleep(0.5)  # polite rate-limit between yfinance calls

        df = ema_mod.fetch_ohlc(ticker, timeframe)
        if df is None:
            continue

        df = ema_mod.add_emas(df)
        signal, price, highest_ema = ema_mod.detect_signal(df)
        bar_ts = ema_mod.last_bar_timestamp(df)

        if signal:
            last_bar = ema_watch[ticker].get("last_signal_bar")
            if bar_ts == last_bar:
                # Already notified for this exact bar — skip
                logger.debug("Duplicate EMA signal suppressed: %s %s bar=%s", ticker, signal, bar_ts)
                print(f"  {ticker}: {signal} already sent for this bar, skipping")
                continue

            msg = notifier.format_ema_alert(signal, ticker, price, timeframe, highest_ema)
            icon = "🟢" if signal == "BUY" else "🔴"
            print(f"  {icon} {signal}: {ticker} @ ${price:.2f} (highest EMA ${highest_ema:.2f})")
            logger.info("EMA signal: %s %s %s @ $%.2f", signal, ticker, timeframe, price)
            notifier.alert(f"{icon} {signal} — {ticker} ({timeframe})", msg)

            ema_watch[ticker]["last_signal"]     = signal
            ema_watch[ticker]["last_signal_bar"] = bar_ts
            changed = True
        else:
            arrow = "▲" if price > highest_ema else "▼"
            print(f"  {ticker}: ${price:.2f}  ({arrow} EMA ${highest_ema:.2f})")

    if changed:
        storage.save(data)


# ---------------------------------------------------------------------------
# CLI commands — price alerts
# ---------------------------------------------------------------------------

def cmd_add(ticker: str, price_str: str, direction: str) -> None:
    ticker    = ticker.upper()
    direction = direction.lower()

    if direction not in ("above", "below"):
        sys.exit("Direction must be 'above' or 'below'.")
    try:
        target = float(price_str)
    except ValueError:
        sys.exit(f"Invalid price: {price_str!r}")

    print(f"Verifying {ticker}…")
    current = get_price(ticker)
    if current is None:
        sys.exit(f"Could not retrieve a price for '{ticker}'. Check the ticker symbol.")

    data = storage.load()
    data["price_alerts"][ticker] = {
        "target_price": target,
        "direction":    direction,
        "added_at":     datetime.now(BKK).isoformat(),
        "alerted":      False,
    }
    storage.save(data)
    print(f"Added {ticker}: alert when price goes {direction} ${target:.2f}  (current: ${current:.2f})")
    logger.info("Price alert added: %s %s $%.2f", ticker, direction, target)


def cmd_remove(ticker: str) -> None:
    ticker = ticker.upper()
    data   = storage.load()
    if ticker not in data["price_alerts"]:
        sys.exit(f"{ticker} is not in the price-alert watchlist.")
    del data["price_alerts"][ticker]
    storage.save(data)
    print(f"Removed {ticker} from price alerts.")
    logger.info("Price alert removed: %s", ticker)


# ---------------------------------------------------------------------------
# CLI commands — EMA watchlist
# ---------------------------------------------------------------------------

def cmd_watch(ticker: str, timeframe: str) -> None:
    ticker    = ticker.upper()
    timeframe = timeframe.lower()

    if timeframe not in ema_mod.VALID_TIMEFRAMES:
        sys.exit(
            f"Invalid timeframe '{timeframe}'. "
            f"Choose from: {', '.join(sorted(ema_mod.VALID_TIMEFRAMES))}"
        )

    print(f"Verifying {ticker} ({timeframe})…")
    df = ema_mod.fetch_ohlc(ticker, timeframe)
    if df is None:
        sys.exit(f"Could not fetch data for '{ticker}'. Check the ticker symbol.")

    data = storage.load()
    data["ema_watchlist"][ticker] = {
        "timeframe":       timeframe,
        "added_at":        datetime.now(BKK).isoformat(),
        "last_signal":     None,
        "last_signal_bar": None,
    }
    storage.save(data)
    print(f"Added {ticker} to EMA watchlist (timeframe: {timeframe}, {len(df)} bars fetched)")
    logger.info("EMA watch added: %s %s", ticker, timeframe)


def cmd_unwatch(ticker: str) -> None:
    ticker = ticker.upper()
    data   = storage.load()
    if ticker not in data["ema_watchlist"]:
        sys.exit(f"{ticker} is not in the EMA watchlist.")
    del data["ema_watchlist"][ticker]
    storage.save(data)
    print(f"Removed {ticker} from EMA watchlist.")
    logger.info("EMA watch removed: %s", ticker)


# ---------------------------------------------------------------------------
# CLI commands — list (combined view)
# ---------------------------------------------------------------------------

def cmd_list() -> None:
    data        = storage.load()
    price_alerts = data["price_alerts"]
    ema_watchlist = data["ema_watchlist"]

    # ── Price alerts ────────────────────────────────────────────────────────
    print("\n=== Price Alerts ===")
    if not price_alerts:
        print("  (none)  — use: python bot.py add <TICKER> <PRICE> <above|below>")
    else:
        print(f"{'Ticker':<8} {'Target':>10} {'Direction':<10} {'Current':>10}  Status")
        print("─" * 54)
        for ticker, cfg in price_alerts.items():
            current     = get_price(ticker)
            current_str = f"${current:.2f}" if current is not None else "N/A"
            status      = "Alerted ✓" if cfg.get("alerted") else "Watching"
            print(
                f"{ticker:<8} ${cfg['target_price']:>9.2f} {cfg['direction']:<10} "
                f"{current_str:>10}  {status}"
            )

    # ── EMA watchlist ────────────────────────────────────────────────────────
    print("\n=== EMA Watchlist ===")
    if not ema_watchlist:
        print("  (none)  — use: python bot.py watch <TICKER> <TIMEFRAME>")
    else:
        print(f"{'Ticker':<8} {'Timeframe':<10} {'Last Signal':<12} Last Signal Bar")
        print("─" * 55)
        for ticker, cfg in ema_watchlist.items():
            sig      = cfg.get("last_signal") or "—"
            bar_time = cfg.get("last_signal_bar") or "—"
            if bar_time != "—":
                bar_time = bar_time[:16]   # trim microseconds/tz suffix for display
            print(f"{ticker:<8} {cfg['timeframe']:<10} {sig:<12} {bar_time}")

    print()


# ---------------------------------------------------------------------------
# CLI commands — run (scheduler)
# ---------------------------------------------------------------------------

def cmd_run() -> None:
    print("Starting Stock Alert Bot…")
    print(f"  Price alerts  : every {PRICE_CHECK_MINUTES} minutes")
    print("  EMA 15m       : every 15 minutes")
    print("  EMA 1h        : every hour")
    print("  EMA 4h        : every 4 hours")
    print("  EMA 1d        : daily at 16:05 New York time (after NYSE close)")
    print("Press Ctrl+C to stop.\n")

    logger.info("Bot started")

    # Run everything once immediately
    check_price_alerts()
    for tf in ema_mod.VALID_TIMEFRAMES:
        check_ema_watchlist(tf)

    # Price-target checks
    schedule.every(PRICE_CHECK_MINUTES).minutes.do(check_price_alerts)

    # EMA checks — interval-matched to timeframe
    schedule.every(15).minutes.do(check_ema_watchlist, "15m")
    schedule.every(1).hours.do(check_ema_watchlist, "1h")
    schedule.every(4).hours.do(check_ema_watchlist, "4h")
    # Daily bars close at 4 PM ET; schedule at 16:05 NY time regardless of server tz
    schedule.every().day.at("16:05", "America/New_York").do(check_ema_watchlist, "1d")

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nBot stopped.")
        logger.info("Bot stopped by user")


# ---------------------------------------------------------------------------
# CLI commands — backtest
# ---------------------------------------------------------------------------

def cmd_backtest(ticker: str, timeframe: str, period: str) -> None:
    ticker    = ticker.upper()
    timeframe = timeframe.lower()
    if timeframe not in ema_mod.VALID_TIMEFRAMES:
        sys.exit(
            f"Invalid timeframe '{timeframe}'. "
            f"Choose from: {', '.join(sorted(ema_mod.VALID_TIMEFRAMES))}"
        )
    backtest_mod.run_backtest(ticker, timeframe, period)


# ---------------------------------------------------------------------------
# CLI commands — test-line
# ---------------------------------------------------------------------------

def cmd_test_line() -> None:
    now = datetime.now(BKK).strftime("%Y-%m-%d %H:%M")
    msg = (
        f"🤖 LINE Test — Stock Alert Bot\n"
        f"Connection successful!\n"
        f"Time: {now} (Bangkok time)"
    )
    print("Sending test message to LINE…")
    ok = notifier.send_line(msg)
    if ok:
        print("✓ Test message sent! Check your LINE app.")
    else:
        print("✗ Failed. Check LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID in your .env file.")
        print("  Run: python bot.py test-line  again after fixing credentials.")


# ---------------------------------------------------------------------------
# CLI commands — test-signal
# ---------------------------------------------------------------------------

def cmd_test_signal(ticker: str) -> None:
    """
    Send fake BUY and SELL alerts to LINE using real current data for ticker.
    Useful for verifying message formatting before relying on live signals.
    Uses the ticker's watchlist timeframe if it exists, otherwise defaults to 1d.
    """
    ticker = ticker.upper()

    # Prefer the timeframe the user already configured for this ticker
    data      = storage.load()
    timeframe = data["ema_watchlist"].get(ticker, {}).get("timeframe", "1d")

    print(f"Fetching {ticker} ({timeframe}) for test signals…")
    df = ema_mod.fetch_ohlc(ticker, timeframe)
    if df is None:
        sys.exit(f"Could not fetch data for '{ticker}'.")

    df = ema_mod.add_emas(df)
    _, price, highest_ema = ema_mod.detect_signal(df)

    buy_msg  = "[TEST]\n" + notifier.format_ema_alert("BUY",  ticker, price, timeframe, highest_ema)
    sell_msg = "[TEST]\n" + notifier.format_ema_alert("SELL", ticker, price, timeframe, highest_ema)

    print(f"\nData  →  {ticker}  |  Price: ${price:.2f}  |  Highest EMA: ${highest_ema:.2f}  |  TF: {timeframe}")
    print("\n── BUY preview ──")
    print(buy_msg)
    print("\n── SELL preview ──")
    print(sell_msg)
    print()

    print("Sending [TEST] BUY to LINE…")
    ok1 = notifier.send_line(buy_msg)
    time.sleep(1)
    print("Sending [TEST] SELL to LINE…")
    ok2 = notifier.send_line(sell_msg)

    if ok1 and ok2:
        print("✓ Both test signals sent! Check your LINE app.")
    elif not ok1 and not ok2:
        print("✗ Both failed. Check LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID in .env")
    else:
        print("⚠ One message failed — check bot.log for details.")

    logger.info("test-signal sent for %s (%s)", ticker, timeframe)


# ---------------------------------------------------------------------------
# CLI commands — report
# ---------------------------------------------------------------------------

def cmd_report() -> None:
    """
    Fetch live EMA data for every ticker in the EMA watchlist, calculate how
    far each price sits above/below the highest EMA, then send a ranked report
    to LINE (and print it to the terminal).

    Sort order: 🟢 ABOVE stocks first (largest % gap at top),
                🔴 BELOW stocks after (closest to crossing at top).
    """
    data          = storage.load()
    ema_watchlist = data["ema_watchlist"]
    now_bkk       = datetime.now(BKK).strftime("%Y-%m-%d %H:%M")
    sep           = "─" * 17

    if not ema_watchlist:
        msg = (
            f"📊 EMA Ribbon Report\n"
            f"{now_bkk} (Bangkok)\n"
            f"{sep}\n"
            f"EMA watchlist is empty.\n"
            f"Add tickers: python bot.py watch <TICKER> <TIMEFRAME>"
        )
        print(msg)
        notifier.send_line(msg)
        return

    print(f"Building EMA report for {len(ema_watchlist)} ticker(s)…")

    results: list[dict] = []
    for ticker, cfg in ema_watchlist.items():
        timeframe = cfg["timeframe"]
        time.sleep(0.5)  # rate-limit between yfinance calls

        try:
            df = ema_mod.fetch_ohlc(ticker, timeframe)
            if df is None:
                print(f"  Skipping {ticker} — data fetch failed")
                logger.warning("Report: skipped %s (no data)", ticker)
                continue

            df = ema_mod.add_emas(df)
            _, price, highest_ema = ema_mod.detect_signal(df)
            pct_diff = (price - highest_ema) / highest_ema * 100

            results.append({
                "ticker":      ticker,
                "timeframe":   timeframe,
                "price":       price,
                "highest_ema": highest_ema,
                "pct_diff":    pct_diff,
                "above":       price > highest_ema,
            })

            icon = "🟢" if price > highest_ema else "🔴"
            sign = "+" if pct_diff >= 0 else ""
            print(f"  {icon} {ticker} ({timeframe}): ${price:.2f}  EMA ${highest_ema:.2f}  {sign}{pct_diff:.2f}%")

        except Exception as e:
            print(f"  Skipping {ticker} — error: {e}")
            logger.error("Report: error for %s: %s", ticker, e)

    if not results:
        msg = f"📊 EMA Ribbon Report\n{now_bkk} (Bangkok)\n{sep}\nNo data available."
        print("\n" + msg)
        notifier.send_line(msg)
        return

    # key=lambda x: -x["pct_diff"] correctly sorts both groups:
    #   ABOVE: largest positive % first (e.g. +5% before +1%)
    #   BELOW: closest to crossing first (e.g. -0.5% before -5%)
    above_list = sorted([r for r in results if r["above"]],     key=lambda x: -x["pct_diff"])
    below_list = sorted([r for r in results if not r["above"]], key=lambda x: -x["pct_diff"])

    lines = [f"📊 EMA Ribbon Report", f"{now_bkk} (Bangkok)", sep]
    for r in above_list + below_list:
        icon   = "🟢" if r["above"] else "🔴"
        status = "ABOVE" if r["above"] else "BELOW"
        sign   = "+" if r["pct_diff"] >= 0 else ""
        lines += [
            f"{icon} {r['ticker']} ({r['timeframe']})",
            f"Price: ${r['price']:.2f}",
            f"Highest EMA: ${r['highest_ema']:.2f}",
            f"Diff: {sign}{r['pct_diff']:.2f}% {status}",
            sep,
        ]

    msg = "\n".join(lines)
    print("\n" + msg)

    ok = notifier.send_line(msg)
    if ok:
        print("\n✓ Report sent to LINE!")
    else:
        print("\n(LINE not configured — report printed to terminal only)")

    logger.info("Report: %d tickers (%d above, %d below)",
                len(results), len(above_list), len(below_list))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

USAGE = """
Stock Price Alert Bot

Price-target commands:
  python bot.py add <TICKER> <PRICE> <above|below>
  python bot.py remove <TICKER>

EMA Ribbon commands:
  python bot.py watch <TICKER> <TIMEFRAME>       TIMEFRAME: 15m | 1h | 4h | 1d
  python bot.py unwatch <TICKER>

General:
  python bot.py list
  python bot.py run
  python bot.py backtest <TICKER> <TIMEFRAME> <PERIOD>   PERIOD: 1mo 3mo 6mo 1y 2y 5y
  python bot.py test-line
  python bot.py test-signal <TICKER>
  python bot.py report

Examples:
  python bot.py add AAPL 200 above
  python bot.py watch TSLA 1d
  python bot.py backtest SPY 1d 2y
  python bot.py test-signal AAPL
  python bot.py report
  python bot.py run
"""


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(USAGE)
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "add":
        if len(args) != 4:
            sys.exit("Usage: python bot.py add <TICKER> <PRICE> <above|below>")
        cmd_add(args[1], args[2], args[3])

    elif cmd == "remove":
        if len(args) != 2:
            sys.exit("Usage: python bot.py remove <TICKER>")
        cmd_remove(args[1])

    elif cmd == "watch":
        if len(args) != 3:
            sys.exit("Usage: python bot.py watch <TICKER> <TIMEFRAME>")
        cmd_watch(args[1], args[2])

    elif cmd == "unwatch":
        if len(args) != 2:
            sys.exit("Usage: python bot.py unwatch <TICKER>")
        cmd_unwatch(args[1])

    elif cmd == "list":
        cmd_list()

    elif cmd == "run":
        cmd_run()

    elif cmd == "backtest":
        if len(args) != 4:
            sys.exit("Usage: python bot.py backtest <TICKER> <TIMEFRAME> <PERIOD>")
        cmd_backtest(args[1], args[2], args[3])

    elif cmd == "test-line":
        cmd_test_line()

    elif cmd == "test-signal":
        if len(args) != 2:
            sys.exit("Usage: python bot.py test-signal <TICKER>")
        cmd_test_signal(args[1])

    elif cmd == "report":
        cmd_report()

    else:
        print(f"Unknown command: {cmd!r}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
