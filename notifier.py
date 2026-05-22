"""Notification layer — macOS desktop alerts and LINE Messaging API."""

import os
import logging
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
BKK = ZoneInfo("Asia/Bangkok")
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


# ---------------------------------------------------------------------------
# macOS desktop
# ---------------------------------------------------------------------------

def send_desktop(title: str, message: str) -> None:
    safe_title = title.replace('"', '\\"').replace("'", "\\'")
    safe_message = message.replace('"', '\\"').replace("'", "\\'")
    script = (
        f'display notification "{safe_message}" '
        f'with title "{safe_title}" sound name "Glass"'
    )
    subprocess.run(["osascript", "-e", script], check=False)


# ---------------------------------------------------------------------------
# LINE Messaging API
# ---------------------------------------------------------------------------

def send_line(text: str) -> bool:
    """Push a text message to the user via LINE Messaging API. Returns True on success."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()

    if not token or not user_id:
        logger.warning("LINE credentials missing from .env — skipping LINE notification")
        return False

    try:
        resp = requests.post(
            LINE_PUSH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"to": user_id, "messages": [{"type": "text", "text": text}]},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.error("LINE API request failed: %s", e)
        return False

    if not resp.ok:
        logger.error("LINE API error %s: %s", resp.status_code, resp.text)
        return False

    logger.info("LINE message sent successfully")
    return True


# ---------------------------------------------------------------------------
# Message formatters
# ---------------------------------------------------------------------------

def _bkk_now() -> str:
    return datetime.now(BKK).strftime("%Y-%m-%d %H:%M")


def format_ema_alert(signal: str, ticker: str, price: float, timeframe: str, highest_ema: float) -> str:
    emoji = "🟢" if signal == "BUY" else "🔴"
    return (
        f"{emoji} {signal} SIGNAL\n"
        f"Ticker: {ticker}\n"
        f"Price: ${price:.2f}\n"
        f"Timeframe: {timeframe}\n"
        f"Highest EMA: ${highest_ema:.2f}\n"
        f"Time: {_bkk_now()} (Bangkok time)"
    )


def format_price_alert(ticker: str, price: float, target: float, direction: str) -> str:
    emoji = "📈" if direction == "above" else "📉"
    return (
        f"{emoji} PRICE ALERT\n"
        f"Ticker: {ticker}\n"
        f"Current Price: ${price:.2f}\n"
        f"Target: {direction} ${target:.2f}\n"
        f"Time: {_bkk_now()} (Bangkok time)"
    )


# ---------------------------------------------------------------------------
# Combined alert (desktop + LINE)
# ---------------------------------------------------------------------------

def alert(title: str, message: str) -> None:
    send_desktop(title, message)
    send_line(message)
