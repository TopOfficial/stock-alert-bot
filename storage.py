"""Persistence layer — all reads and writes to watchlist.json go through here."""

import json
from pathlib import Path

WATCHLIST_FILE = Path(__file__).parent / "watchlist.json"


def load() -> dict:
    """Return the full watchlist dict, migrating the old flat format if needed."""
    if not WATCHLIST_FILE.exists():
        return {"price_alerts": {}, "ema_watchlist": {}}

    with open(WATCHLIST_FILE) as f:
        data = json.load(f)

    # Migrate: old format had ticker symbols as top-level keys
    if "price_alerts" not in data and "ema_watchlist" not in data:
        return {"price_alerts": data, "ema_watchlist": {}}

    data.setdefault("price_alerts", {})
    data.setdefault("ema_watchlist", {})
    return data


def save(data: dict) -> None:
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)
