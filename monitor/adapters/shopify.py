from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from .. import http
from ..filters import wanted_title
from .base import AdapterError

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


@dataclass
class ShopItem:
    shop: str
    id: int
    title: str
    url: str
    price: Optional[float]
    available: bool

    @property
    def key(self) -> str:
        return f"{self.shop}:{self.id}"


def _created_ts(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def parse_products(shop: str, base: str, products: list[dict], since_ts: float, allow_non_english: bool = False) -> list[ShopItem]:
    items = []
    for p in products:
        created = _created_ts(p.get("created_at"))
        if created is not None and created < since_ts:
            continue
        if not wanted_title(p.get("title", ""), allow_non_english):
            continue
        variants = p.get("variants") or []
        avail = [v for v in variants if v.get("available")]
        pick = (avail or variants or [{}])[0]
        price = pick.get("price")
        items.append(
            ShopItem(
                shop=shop,
                id=p["id"],
                title=p["title"],
                url=f"{base}/products/{p['handle']}",
                price=float(price) if price not in (None, "") else None,
                available=bool(avail),
            )
        )
    return items


def _fetch_collection(client: httpx.Client, base: str, handle: str) -> list[dict]:
    out: list[dict] = []
    for page in range(1, 6):
        r = http.get(client, f"{base}/collections/{handle}/products.json", f"{base} collection {handle}", {"limit": 250, "page": page})
        try:
            batch = r.json().get("products", [])
        except ValueError as e:
            raise AdapterError(f"{base} returned non-JSON for collection {handle}") from e
        out.extend(batch)
        if len(batch) < 250:
            break
        time.sleep(0.5)
    return out


def discover(shop: dict, since: str = "2025-01-01") -> list[ShopItem]:
    """Fetch the configured collections of a Shopify shop and keep wanted, recent Pokémon products."""
    since_ts = datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp()
    base = shop["base"].rstrip("/")
    found: dict[int, ShopItem] = {}
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for handle in shop["collections"]:
            products = _fetch_collection(client, base, handle)
            for it in parse_products(shop["name"], base, products, since_ts, shop.get("allow_non_english", False)):
                found.setdefault(it.id, it)
            time.sleep(0.5)
    return list(found.values())


def search(base: str, query: str, limit: int = 10) -> list[ShopItem]:
    """Search a Shopify shop (including sold-out products) for a card/product name via the predictive search API."""
    base = base.rstrip("/")
    params = {
        "q": query,
        "resources[type]": "product",
        "resources[limit]": limit,
        "resources[options][unavailable_products]": "last",
    }
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        r = http.get(client, f"{base}/search/suggest.json", f"{base} search", params)
    try:
        products = r.json()["resources"]["results"]["products"]
    except (ValueError, KeyError) as e:
        raise AdapterError(f"{base} returned unexpected search JSON") from e
    items = []
    for p in products:
        price = p.get("price")
        items.append(
            ShopItem(
                shop=base,
                id=p["id"],
                title=p["title"],
                url=base + p["url"].split("?")[0],
                price=float(price) if price not in (None, "") else None,
                available=bool(p.get("available")),
            )
        )
    return items
