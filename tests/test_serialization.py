import pytest
from scrapy import Request

from scrapy_zyte_api import ScrapyZyteAPISessionDownloaderMiddleware, Session
from scrapy_zyte_api._page_inputs import Actions, Geolocation, Screenshot


@pytest.mark.parametrize(
    "case",
    [
        {"cls": Actions, "kwargs": {"results": [{"action": "click", "id": "x"}]}},
        {"cls": Geolocation, "kwargs": {}},
        {"cls": Screenshot, "kwargs": {"body": b"PNGDATA"}},
    ],
)
def test(case):
    wp = pytest.importorskip("web_poet.serialization")
    cls = case["cls"]
    kwargs = case["kwargs"]

    obj = cls(**kwargs)
    data = wp.serialize_leaf(obj)
    reconstructed = wp.deserialize_leaf(cls, data)

    assert reconstructed == obj
    assert id(reconstructed) != id(obj)


def test_session():
    """A live Session serializes to no data, and deserializing it yields a
    Session with no session to discard, e.g. when replaying page objects from a
    fixture or from SCRAPY_POET_CACHE."""
    wp = pytest.importorskip("web_poet.serialization")

    middleware = ScrapyZyteAPISessionDownloaderMiddleware.__new__(
        ScrapyZyteAPISessionDownloaderMiddleware
    )
    obj = Session(middleware=middleware, request=Request("https://example.com"))
    data = wp.serialize_leaf(obj)

    assert data == {}
    assert wp.deserialize_leaf(Session, data) == Session()
