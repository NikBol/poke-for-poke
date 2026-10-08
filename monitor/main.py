from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
import yaml

from . import notify, state as st
from .adapters import ADAPTERS, shopify, webhallen
from .adapters.base import AdapterError

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yaml"
STATE = Path(os.environ.get("STATE_FILE", ROOT / "state.json"))


FAILS_BEFORE_ALERT = 3


def _failed(state: dict, key: str, msg: str) -> bool:
    """Count consecutive failures; push one alert when it reaches the threshold (transient 429s stay quiet)."""
    counts = state.setdefault("fail_counts", {})
    counts[key] = counts.get(key, 0) + 1
    if counts[key] == FAILS_BEFORE_ALERT:
        notify.send("Monitor adapter problem", f"{msg} (failed {FAILS_BEFORE_ALERT} runs in a row)", priority="low")
        return True
    return False


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
        _failed(state, "webhallen", f"webhallen: {e}")
        return 1
    state.setdefault("fail_counts", {})["webhallen"] = 0
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


def run_shop(shop: dict, since: str, state: dict) -> int:
    name = shop["name"]
    if not st.due(state, f"shop:{name}", shop.get("every_minutes")):
        print(f"[skip] {name}: checked less than {shop['every_minutes']} min ago")
        return 0
    st.mark_checked(state, f"shop:{name}")
    try:
        items = shopify.discover(shop, since=since)
    except AdapterError as e:
        print(f"[error] {name}: {e}")
        _failed(state, f"shop:{name}", f"{name}: {e}")
        return 1
    state.setdefault("fail_counts", {})[f"shop:{name}"] = 0
    # First time we see a shop, only record what is in stock; otherwise every item already on the shelf would alert.
    baseline = name not in state.setdefault("shops_seen", [])
    for it in items:
        prev = state["products"].get(it.key, {})
        print(f"[ok] {name}: {it.title} available={it.available} price={it.price}")
        now = "in_stock" if it.available else "out_of_stock"
        if not baseline and st.should_alert(prev.get("stock"), now, it.price, shop.get("max_price")):
            price = f"{it.price:g} kr" if it.price is not None else "price unknown"
            notify.send(f"{name}: {it.title} in stock", f"{it.title} is available for {price}", click_url=it.url, priority="high")
        state["products"][it.key] = {"name": it.title, "stock": now, "price": it.price, "error": None}
    if baseline:
        state["shops_seen"].append(name)
        print(f"[baseline] {name}: recorded {len(items)} products without alerting")
    return 0


def run_watch(w: dict, state: dict) -> int:
    """Watch for a specific card/product by name across shops: alert on new listings and on restocks."""
    label = w["name"]
    needle = w["match"].lower()
    baseline_key = f"watch:{label}"
    baseline = baseline_key not in state.setdefault("shops_seen", [])
    code = 0
    for shop in w["shops"]:
        fail_key = f"watch:{label}:{shop['name']}"
        if not st.due(state, fail_key, shop.get("every_minutes")):
            print(f"[skip] watch {label} @ {shop['name']}: checked less than {shop['every_minutes']} min ago")
            continue
        st.mark_checked(state, fail_key)
        try:
            items = [i for i in shopify.search(shop["base"], w["match"]) if needle in i.title.lower()]
        except AdapterError as e:
            print(f"[error] watch {label} @ {shop['name']}: {e}")
            _failed(state, fail_key, f"{label} @ {shop['name']}: {e}")
            code = 1
            continue
        state.setdefault("fail_counts", {})[fail_key] = 0
        for it in items:
            key = f"watch:{shop['name']}:{it.id}"
            known = key in state["products"]
            prev = state["products"].get(key, {})
            now = "in_stock" if it.available else "out_of_stock"
            print(f"[ok] watch {shop['name']}: {it.title} {now} price={it.price}")
            price = f"{it.price:g} kr" if it.price is not None else "price unknown"
            if not baseline:
                if st.should_alert(prev.get("stock"), now, it.price, w.get("max_price")):
                    notify.send(f"{shop['name']}: {it.title} IN STOCK", f"{price}", click_url=it.url, priority="urgent")
                elif not known and w.get("notify_new_listing", True):
                    notify.send(f"{shop['name']}: new listing {it.title}", f"Not in stock yet ({price})", click_url=it.url)
            state["products"][key] = {"name": it.title, "stock": now, "price": it.price, "error": None}
    if baseline and code == 0:
        state["shops_seen"].append(baseline_key)
        print(f"[baseline] watch {label}")
    return code


def ping_healthcheck() -> None:
    ping = os.environ.get("HEALTHCHECK_URL")
    if ping:
        try:
            httpx.get(ping, timeout=10)
        except httpx.HTTPError:
            pass


def run() -> int:
    config = yaml.safe_load(CONFIG.read_text())
    quiet = config.get("quiet_hours")
    if st.in_quiet(time.time(), quiet):
        print(f"[quiet] {quiet['start']}-{quiet['end']} {quiet.get('timezone', 'UTC')}: skipping checks")
        ping_healthcheck()  # the dead-man's switch should not fire overnight
        return 0
    state = st.load(STATE)
    errors = 0

    gap = st.stale_gap_minutes(state, quiet=quiet)
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

    for shop in config.get("shops") or []:
        errors += run_shop(shop, config.get("shop_since", "2025-01-01"), state)

    for w in config.get("watchlist") or []:
        errors += run_watch(w, state)

    # A run that finished means the monitor is alive again; re-arm the stale alert.
    state["last_run_ts"] = time.time()
    state["alerted_stale"] = False
    st.save(STATE, state)

    ping_healthcheck()
    return 0


if __name__ == "__main__":
    sys.exit(run())
