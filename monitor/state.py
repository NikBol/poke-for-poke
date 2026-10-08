from __future__ import annotations

import json
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

STALE_AFTER_SECONDS = 30 * 60


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"products": {}, "last_run_ts": None, "alerted_stale": False}


def save(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _windows(start_ts: float, end_ts: float, quiet: dict):
    """Yield (start, end) timestamps of each quiet window that could overlap [start_ts, end_ts]."""
    tz = ZoneInfo(quiet.get("timezone", "UTC"))
    qs = dtime.fromisoformat(quiet["start"])
    qe = dtime.fromisoformat(quiet["end"])
    day = datetime.fromtimestamp(start_ts, tz).date() - timedelta(days=1)
    last_day = datetime.fromtimestamp(end_ts, tz).date()
    while day <= last_day:
        w_start = datetime.combine(day, qs, tzinfo=tz)
        w_end = datetime.combine(day, qe, tzinfo=tz)
        if w_end <= w_start:  # window crosses midnight
            w_end += timedelta(days=1)
        yield w_start.timestamp(), w_end.timestamp()
        day += timedelta(days=1)


def in_quiet(now: float, quiet: Optional[dict]) -> bool:
    if not quiet:
        return False
    return any(a <= now < b for a, b in _windows(now, now, quiet))


def quiet_overlap(start_ts: float, end_ts: float, quiet: Optional[dict]) -> float:
    if not quiet:
        return 0.0
    return sum(max(0.0, min(end_ts, b) - max(start_ts, a)) for a, b in _windows(start_ts, end_ts, quiet))


def stale_gap_minutes(state: dict, now: Optional[float] = None, quiet: Optional[dict] = None) -> Optional[int]:
    """Minutes since the previous run if it exceeds the threshold and we haven't alerted yet, else None.

    Quiet hours (when no checks are meant to run) don't count towards the gap.
    """
    now = time.time() if now is None else now
    last = state.get("last_run_ts")
    if last is None or state.get("alerted_stale"):
        return None
    gap = now - last - quiet_overlap(last, now, quiet)
    return int(gap // 60) if gap > STALE_AFTER_SECONDS else None


def due(state: dict, key: str, every_minutes: Optional[float], now: Optional[float] = None) -> bool:
    """True if `key` should be checked this run. Shops with `every_minutes` are checked less often than the run rate.

    A minute of slack absorbs timer jitter. The attempt time is recorded by the caller, success or not,
    so a throttled shop is not hammered every run.
    """
    if not every_minutes:
        return True
    now = time.time() if now is None else now
    last = state.get("last_checked", {}).get(key)
    return last is None or now - last >= every_minutes * 60 - 60


def mark_checked(state: dict, key: str, now: Optional[float] = None) -> None:
    state.setdefault("last_checked", {})[key] = time.time() if now is None else now


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
