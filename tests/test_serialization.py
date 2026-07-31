import pytest

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
