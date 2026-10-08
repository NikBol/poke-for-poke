from __future__ import annotations

import time
from typing import Optional

import httpx

from .adapters.base import AdapterError

RETRY_STATUSES = (429, 503)
MAX_RETRIES = 2
MAX_WAIT = 20.0


def _wait_seconds(r: httpx.Response, attempt: int) -> float:
    try:
        return min(float(r.headers.get("retry-after", "")), MAX_WAIT)
    except ValueError:
        return 4.0 * (attempt + 1)


def describe_block(r: httpx.Response) -> str:
    """Details that help tell a rate limit from a datacenter-IP block (shown in the log and the alert)."""
    h = r.headers
    bits = [f"HTTP {r.status_code}"]
    for name in ("retry-after", "server", "cf-ray", "x-shopify-shop-api-call-limit"):
        if h.get(name):
            bits.append(f"{name}={h[name]}")
    return ", ".join(bits)


def get(client: httpx.Client, url: str, what: str, params: Optional[dict] = None) -> httpx.Response:
    """GET with a couple of polite retries on 429/503; raises AdapterError with block details if it persists."""
    r = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = client.get(url, params=params, timeout=20)
        except httpx.HTTPError as e:
            raise AdapterError(f"{what} request failed: {e}") from e
        if r.status_code not in RETRY_STATUSES:
            break
        if attempt < MAX_RETRIES:
            time.sleep(_wait_seconds(r, attempt))
    if r.status_code in (403, 429, 503):
        raise AdapterError(f"{what} blocked or rate limited ({describe_block(r)})")
    if r.status_code != 200:
        raise AdapterError(f"{what} HTTP {r.status_code}")
    return r
