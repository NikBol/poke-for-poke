from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Stock(str, Enum):
    IN_STOCK = "in_stock"
    PREORDER = "preorder_available_for_you"
    OUT_OF_STOCK = "out_of_stock"


@dataclass
class StockResult:
    stock: Stock
    price: Optional[float] = None
    title: Optional[str] = None


class AdapterError(Exception):
    """Raised when a page can't be interpreted (blocked, captcha, layout change).

    Must never be mapped to OUT_OF_STOCK, otherwise a broken adapter looks like "nothing to buy".
    """


class Adapter:
    name = "base"

    def check(self, url: str, **options) -> StockResult:
        raise NotImplementedError
