from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import httpx

from .base import AdapterError

API = "https://www.webhallen.com/api"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Things worth alerting on: ETBs, multi-pack bundles/boxes, and anything 30th Celebration.
WANTED = re.compile(
    r"elite trainer|\betb\b|booster bundle|bundle|build & battle|collection|ultra[- ]premium|"
    r"booster box|display|tin\b|\bbox\b",
    re.I,
)
# Accessories are skipped unless they are 30th Celebration items.
ACCESSORY = re.compile(r"sleeve|binder|playmat|portfolio|deck box|plush|album|figure|pin\b|mugg|t-shirt", re.I)


@dataclass
class WebhallenItem:
    id: int
    name: str
    url: str
    price: Optional[float]
    web_stock: int
    min_level: Optional[int] = None  # filled from the detail endpoint when there is stock
    shippable: Optional[bool] = None
    max_qty: Optional[int] = None

    @property
    def key(self) -> str:
        return f"webhallen:{self.id}"


def wanted(name: str, category_tree: str, release_ts: Optional[int], since_ts: int) -> bool:
    if "pok" not in category_tree.lower() and "pokemon" not in name.lower():
        return False
    if release_ts is not None and release_ts < since_ts:
        return False
    is_30th = "30th" in name.lower()
    if ACCESSORY.search(name) and not is_30th:
        return False
    return is_30th or bool(WANTED.search(name))


def parse_search(data: dict, since_ts: int) -> list[WebhallenItem]:
    items = []
    for p in data.get("products") or []:
        release = (p.get("release") or {}).get("timestamp")
        if not wanted(p.get("name", ""), p.get("categoryTree") or "", release, since_ts):
            continue
        price = (p.get("price") or {}).get("price")
        web = (p.get("stock") or {}).get("web") or 0
        items.append(
            WebhallenItem(
                id=p["id"],
                name=p["name"],
                url=f"https://www.webhallen.com/se/product/{p['id']}",
                price=float(price) if price not in (None, "") else None,
                web_stock=int(web),
            )
        )
    return items


def apply_detail(item: WebhallenItem, data: dict) -> WebhallenItem:
    p = data.get("product", data)
    item.min_level = p.get("minimumRankLevel")
    item.shippable = p.get("isShippable")
    item.web_stock = int((p.get("stock") or {}).get("web") or 0)
    limit = p.get("saleLimit") or {}
    item.max_qty = limit.get("maxQtyPerCustomer")
    price = (p.get("price") or {}).get("price")
    if price not in (None, ""):
        item.price = float(price)
    return item


def _get(client: httpx.Client, path: str) -> dict:
    try:
        r = client.get(f"{API}/{path}", timeout=20)
    except httpx.HTTPError as e:
        raise AdapterError(f"webhallen request failed: {e}") from e
    if r.status_code in (403, 429, 503):
        raise AdapterError(f"webhallen blocked or rate limited (HTTP {r.status_code})")
    if r.status_code != 200:
        raise AdapterError(f"webhallen HTTP {r.status_code} for {path}")
    try:
        return r.json()
    except ValueError as e:
        raise AdapterError(f"webhallen returned non-JSON for {path}") from e


def discover(queries: list[str], since: str = "2025-01-01", pages: int = 2) -> list[WebhallenItem]:
    """Search Webhallen for wanted Pokémon products and fetch level info for anything in stock."""
    since_ts = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp())
    found: dict[int, WebhallenItem] = {}
    with httpx.Client(headers=HEADERS) as client:
        for q in queries:
            for page in range(1, pages + 1):
                data = _get(client, f"productdiscovery/search/{quote(q)}?page={page}&touchpoint=MOBILE&origin=ORGANIC")
                batch = parse_search(data, since_ts)
                if not data.get("products"):
                    break
                for it in batch:
                    found.setdefault(it.id, it)
                time.sleep(0.5)
        for it in found.values():
            if it.web_stock > 0:
                apply_detail(it, _get(client, f"product/{it.id}"))
                time.sleep(0.5)
    return list(found.values())
