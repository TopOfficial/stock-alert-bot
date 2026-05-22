"""EMA Ribbon Strategy — data fetching, indicator calculation, and signal detection."""

import logging
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

EMA_PERIODS = [5, 12, 34, 55, 100, 200]
VALID_TIMEFRAMES = {"15m", "1h", "4h", "1d"}

# yfinance fetch config per timeframe; 4h is resampled from 1h
TIMEFRAME_CONFIG = {
    "15m": {"interval": "15m", "period": "60d"},
    "1h":  {"interval": "1h",  "period": "60d"},
    "4h":  {"interval": "1h",  "period": "60d"},
    "1d":  {"interval": "1d",  "period": "2y"},
}


def fetch_ohlc(ticker: str, timeframe: str, period_override: str | None = None) -> pd.DataFrame | None:
    """
    Download OHLC bars for ticker/timeframe via yfinance.
    Returns a DataFrame with columns Open/High/Low/Close/Volume, or None on failure.
    """
    cfg = TIMEFRAME_CONFIG[timeframe]
    period = period_override or cfg["period"]

    try:
        df = yf.Ticker(ticker).history(interval=cfg["interval"], period=period)
    except Exception as e:
        logger.error("yfinance error fetching %s (%s): %s", ticker, timeframe, e)
        return None

    if df is None or df.empty:
        logger.warning("No data returned for %s (%s)", ticker, timeframe)
        return None

    if timeframe == "4h":
        df = (
            df.resample("4h")
            .agg({"Open": "first", "High": "max", "Low": "min",
                  "Close": "last", "Volume": "sum"})
            .dropna(subset=["Close"])
        )

    if len(df) < 3:
        logger.warning("Too few bars (%d) for %s (%s)", len(df), ticker, timeframe)
        return None

    return df


def add_emas(df: pd.DataFrame) -> pd.DataFrame:
    """Add ema_5 … ema_200 columns and a highest_ema column to df (in-place)."""
    for p in EMA_PERIODS:
        df[f"ema_{p}"] = df["Close"].ewm(span=p, adjust=False).mean()
    df["highest_ema"] = df[[f"ema_{p}" for p in EMA_PERIODS]].max(axis=1)
    return df


def detect_signal(df: pd.DataFrame) -> tuple[str | None, float, float]:
    """
    Check for an EMA ribbon crossover on the most recent completed bar.

    Mirrors Pine Script's ta.crossover / ta.crossunder logic:
      BUY  — close was BELOW highest EMA on bar[-2], now ABOVE on bar[-1]
      SELL — close was ABOVE highest EMA on bar[-2], now BELOW on bar[-1]

    Returns (signal, close_price, highest_ema).
    signal is 'BUY', 'SELL', or None.
    """
    close = df["Close"]
    h_ema = df["highest_ema"]

    c0, e0 = float(close.iloc[-1]), float(h_ema.iloc[-1])   # latest bar
    c1, e1 = float(close.iloc[-2]), float(h_ema.iloc[-2])   # previous bar

    if c0 > e0 and c1 < e1:
        return "BUY", c0, e0
    if c0 < e0 and c1 > e1:
        return "SELL", c0, e0
    return None, c0, e0


def last_bar_timestamp(df: pd.DataFrame) -> str:
    """ISO timestamp of the last bar — used to deduplicate repeated alerts."""
    return df.index[-1].isoformat()
