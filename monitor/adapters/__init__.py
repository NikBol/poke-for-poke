from __future__ import annotations

from .base import Adapter
from .jsonld import JsonLdAdapter

# Retailer name (as used in config.yaml) -> adapter. Webhallen and Amazon are added in later milestones.
ADAPTERS: dict[str, Adapter] = {
    "jsonld": JsonLdAdapter(),
}
