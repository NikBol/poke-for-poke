from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
import yaml

from . import notify, state as st
from .adapters import ADAPTERS, webhallen
from .adapters.base import AdapterError

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yaml"
STATE = Path(os.environ.get("STATE_FILE", ROOT / "state.json"))


def webhallen_message(it, my_level):
    lvl = it.min_level
    price = f"{it.price:g} kr" if it.price is not None else "price unknown"
    who = f"level {lvl}+" if lvl else "everyone"
    if lvl is None or my_level is None or lvl <= my_level:
        you = "YOU CAN BUY NOW (your level is enough)"
        priority = "urgent"
    else:
        you = f"not yet for you (you are level {my_level}), get ready"
        priority = "high"
    extras = []
    if it.max_qty:
        extras.append(f"max {it.max_qty}/customer")
    if it.shippable is False:
        extras.append("pickup only?")
    tail = f" ({', '.join(extras)})" if extras else ""
    return (
        f"Webhallen: {it.name} can now be bought by {who} for {price}",
        f"{you}{tail}",
        priority,
    )


def run_webhallen(wh: dict, my_level, state: dict) -> int:
    try:
        items = webhallen.discover(wh["queries"], since=wh.get("since", "2025-01-01"))
    except AdapterError as e:
        print(f"[error] webhallen: {e}")
        if not state.get("webhallen_error"):
            notify.send("Monitor adapter problem", f"webhallen: {e}", priority="low")
        state["webhallen_error"] = str(e)
        return 1
    state["webhallen_error"] = None
    for it in items:
        prev = state["products"].get(it.key, {})
        print(f"[ok] {it.name}: web_stock={it.web_stock} min_level={it.min_level} price={it.price}")
        if st.level_alert(prev, it.web_stock, it.min_level, it.price, wh.get("max_price")):
            title, body, prio = webhallen_message(it, my_level)
            notify.send(title, body, click_url=it.url, priority=prio)
        state["products"][it.key] = {
            "name": it.name,
            "buyable": it.web_stock > 0,
            "level": it.min_level if it.web_stock > 0 else None,
            "price": it.price,
        }
    return 0


def run() -> int:
    config = yaml.safe_load(CONFIG.read_text())
    state = st.load(STATE)
    errors = 0

    gap = st.stale_gap_minutes(state)
    if gap is not None:
        notify.send("Pokémon monitor was delayed", f"No check ran for ~{gap} min. Stock changes in that window may have been missed.")
        state["alerted_stale"] = True

    for p in config["products"]:
        key = p["name"]
        prev = state["products"].get(key, {})
        adapter = ADAPTERS[p["retailer"]]
        try:
            res = adapter.check(p["url"], my_level=config.get("my_level"))
        except AdapterError as e:
            errors += 1
            print(f"[error] {key}: {e}")
            # Alert once when a product starts failing, not on every 5-min run.
            if not prev.get("error"):
                notify.send("Monitor adapter problem", f"{key}: {e}", priority="low")
            state["products"][key] = {**prev, "error": str(e)}
            continue

        print(f"[ok] {key}: {res.stock.value} price={res.price}")
        if st.should_alert(prev.get("stock"), res.stock.value, res.price, p.get("max_price")):
            label = "Preorder open for you" if res.stock.value == "preorder_available_for_you" else "IN STOCK"
            price = f" – {res.price}" if res.price is not None else ""
            notify.send(f"{label}: {key}", f"{res.title or key}{price}", click_url=p["url"], priority="high")
        state["products"][key] = {"stock": res.stock.value, "price": res.price, "error": None}

    wh = config.get("webhallen")
    if wh:
        errors += run_webhallen(wh, config.get("my_level"), state)

    # A run that finished means the monitor is alive again; re-arm the stale alert.
    state["last_run_ts"] = time.time()
    state["alerted_stale"] = False
    st.save(STATE, state)

    ping = os.environ.get("HEALTHCHECK_URL")
    if ping:
        try:
            httpx.get(ping, timeout=10)
        except httpx.HTTPError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(run())
