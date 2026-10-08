from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

STALE_AFTER_SECONDS = 30 * 60


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"products": {}, "last_run_ts": None, "alerted_stale": False}


def save(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def stale_gap_minutes(state: dict, now: Optional[float] = None) -> Optional[int]:
    """Minutes since the previous run if it exceeds the threshold and we haven't alerted yet, else None."""
    now = time.time() if now is None else now
    last = state.get("last_run_ts")
    if last is None or state.get("alerted_stale"):
        return None
    gap = now - last
    return int(gap // 60) if gap > STALE_AFTER_SECONDS else None


def level_alert(prev: dict, web_stock: int, level: Optional[int], price: Optional[float], max_price: Optional[float]) -> bool:
    """Webhallen: alert when a product becomes buyable, then again each time the level requirement changes.

    The first push (e.g. level 26) lets you get ready; later pushes follow the level down towards yours.
    """
    if web_stock <= 0:
        return False
    if max_price is not None and price is not None and price > max_price:
        return False
    if not prev.get("buyable"):
        return True
    return prev.get("level") != level


def should_alert(prev: Optional[str], current: str, price: Optional[float], max_price: Optional[float]) -> bool:
    """Alert only on a transition into a buyable state, and only if the price is acceptable."""
    buyable = current in ("in_stock", "preorder_available_for_you")
    was_buyable = prev in ("in_stock", "preorder_available_for_you")
    if not buyable or was_buyable:
        return False
    return max_price is None or price is None or price <= max_price
