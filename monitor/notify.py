from __future__ import annotations

import os
from typing import Optional

import httpx


def send(title: str, message: str, click_url: Optional[str] = None, priority: str = "default") -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[notify:no NTFY_TOPIC] {title}: {message}")
        return
    base = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    headers = {"Title": title.encode("utf-8"), "Priority": priority, "Tags": "package"}
    if click_url:
        headers["Click"] = click_url
    httpx.post(f"{base}/{topic}", content=message.encode("utf-8"), headers=headers, timeout=15).raise_for_status()
