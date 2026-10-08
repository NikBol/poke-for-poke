import pytest

from monitor.adapters.base import AdapterError, Stock
from monitor.adapters.jsonld import parse_jsonld


def page(avail: str) -> str:
    return f"""<html><head><script type="application/ld+json">
    {{"@type":"Product","name":"Test ETB","offers":{{"@type":"Offer","price":"499","availability":"https://schema.org/{avail}"}}}}
    </script></head></html>"""


def test_in_stock():
    r = parse_jsonld(page("InStock"))
    assert r.stock == Stock.IN_STOCK and r.price == 499.0 and r.title == "Test ETB"


def test_out_of_stock():
    assert parse_jsonld(page("OutOfStock")).stock == Stock.OUT_OF_STOCK


def test_preorder():
    assert parse_jsonld(page("PreOrder")).stock == Stock.PREORDER


def test_unparseable_is_error_not_out_of_stock():
    with pytest.raises(AdapterError):
        parse_jsonld("<html>captcha</html>")
