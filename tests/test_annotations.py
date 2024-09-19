import pytest

from scrapy_zyte_api._annotations import (
    _from_hashable,
    actions,
    custom_attrs,
    make_hashable,
)


@pytest.mark.parametrize(
    "input,expected",
    [
        ([], ()),
        ({}, frozenset()),
        ("foo", "foo"),
        (["foo"], ("foo",)),
        (42, 42),
        (
            {"action": "foo", "id": "xx"},
            frozenset({("action", "foo"), ("id", "xx")}),
        ),
        (
            [{"action": "foo", "id": "xx"}, {"action": "bar"}],
            (
                frozenset({("action", "foo"), ("id", "xx")}),
                frozenset({("action", "bar")}),
            ),
        ),
        (
            {"action": "foo", "options": {"a": "b", "c": ["d", "e"]}},
            frozenset(
                {
                    ("action", "foo"),
                    ("options", frozenset({("a", "b"), ("c", ("d", "e"))})),
                }
            ),
        ),
    ],
)
def test_make_hashable(input, expected):
    assert make_hashable(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        ((), []),
        (frozenset(), {}),
        ("foo", "foo"),
        (("foo",), ["foo"]),
        (42, 42),
        (
            frozenset({("action", "foo"), ("id", "xx")}),
            {"action": "foo", "id": "xx"},
        ),
        (
            (
                frozenset({("action", "foo"), ("id", "xx")}),
                frozenset({("action", "bar")}),
            ),
            [{"action": "foo", "id": "xx"}, {"action": "bar"}],
        ),
        (
            frozenset(
                {
                    ("action", "foo"),
                    ("options", frozenset({("a", "b"), ("c", ("d", "e"))})),
                }
            ),
            {"action": "foo", "options": {"a": "b", "c": ["d", "e"]}},
        ),
    ],
)
def test_from_hashable(input, expected):
    assert _from_hashable(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        ([], ()),
        ([{}], (frozenset(),)),
        (
            [{"action": "foo"}, {"action": "bar"}],
            (
                frozenset({("action", "foo")}),
                frozenset({("action", "bar")}),
            ),
        ),
    ],
)
def test_actions(input, expected):
    assert actions(input) == expected


@pytest.mark.parametrize(
    "input,options,expected",
    [
        ({}, None, (frozenset(), None)),
        ({"foo": "bar"}, None, (frozenset({("foo", "bar")}), None)),
        (
            {"foo": "bar"},
            {"tokens": 42},
            (frozenset({("foo", "bar")}), frozenset({("tokens", 42)})),
        ),
    ],
)
def test_custom_attrs(input, options, expected):
    assert custom_attrs(input, options) == expected
