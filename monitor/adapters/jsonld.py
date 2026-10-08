from __future__ import annotations

import json
from typing import Any, Iterator, Optional

import httpx
from bs4 import BeautifulSoup

from .base import Adapter, AdapterError, Stock, StockResult

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


def _walk(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def parse_jsonld(html: str) -> StockResult:
    """Extract availability from schema.org Product/Offer JSON-LD, used by many shops."""
    soup = BeautifulSoup(html, "html.parser")
    title: Optional[str] = None
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        for obj in _walk(data):
            if obj.get("@type") == "Product":
                title = obj.get("name") or title
            availability = obj.get("availability")
            if not availability:
                continue
            avail = str(availability).rsplit("/", 1)[-1]
            price = obj.get("price")
            price_f = float(price) if price not in (None, "") else None
            if avail in ("InStock", "OnlineOnly", "LimitedAvailability"):
                return StockResult(Stock.IN_STOCK, price_f, title)
            if avail in ("PreOrder", "PreSale"):
                return StockResult(Stock.PREORDER, price_f, title)
            if avail in ("OutOfStock", "SoldOut", "Discontinued", "BackOrder"):
                return StockResult(Stock.OUT_OF_STOCK, price_f, title)
    raise AdapterError("no schema.org availability found in page")


class JsonLdAdapter(Adapter):
    name = "jsonld"

    def check(self, url: str, **options) -> StockResult:
        try:
            r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        except httpx.HTTPError as e:
            raise AdapterError(f"request failed: {e}") from e
        if r.status_code in (403, 429, 503):
            raise AdapterError(f"blocked or rate limited (HTTP {r.status_code})")
        if r.status_code != 200:
            raise AdapterError(f"unexpected HTTP {r.status_code}")
        return parse_jsonld(r.text)
