from collections.abc import Iterable
from enum import Enum
from typing import Any, TypedDict


class ExtractFrom(str, Enum):
    """:ref:`Annotation <annotations>` to specify the :ref:`extraction source
    <zapi-extract-from>` of an automatic extraction :ref:`input <inputs>`,
    such as :class:`~zyte_common_items.Product` or
    :class:`~zyte_common_items.Article`.

    See :ref:`annotations`.
    """

    httpResponseBody = "httpResponseBody"
    browserHtml = "browserHtml"


class _Selector(TypedDict, total=False):
    type: str
    value: str
    state: str | None


class Action(TypedDict, total=False):
    action: str
    address: dict | None
    args: dict | None
    button: str | None
    delay: float | None
    id: str | None
    key: str | None
    keyword: str | None
    left: int | None
    maxPageHeight: int | None
    maxScrollCount: int | None
    maxScrollDelay: float | None
    onError: str | None
    options: dict | None
    selector: _Selector | None
    source: str | None
    text: str | None
    timeout: float | None
    top: int | None
    url: str | None
    urlMatchingOptions: str | None
    urlPattern: str | None
    values: list[str] | None
    waitForNavigationTimeout: float | None
    waitUntil: str | None


class _ActionResult(TypedDict, total=False):  # noqa: PYI049
    action: str
    elapsedTime: float
    status: str
    error: str | None


def make_hashable(obj: Any) -> Any:
    """Converts input into hashable form, to use in ``Annotated``."""
    if isinstance(obj, (tuple, list)):
        return tuple(make_hashable(e) for e in obj)

    if isinstance(obj, dict):
        return frozenset((make_hashable(k), make_hashable(v)) for k, v in obj.items())

    return obj


def _from_hashable(obj: Any) -> Any:
    """Converts a result of ``make_hashable`` back to original form."""
    if isinstance(obj, tuple):
        return [_from_hashable(o) for o in obj]

    if isinstance(obj, frozenset):
        return {_from_hashable(k): _from_hashable(v) for k, v in obj}

    return obj


def actions(value: Iterable[Action]) -> tuple[Any, ...]:
    """Convert an iterable of :class:`~scrapy_zyte_api.Action` dicts into a hashable value."""
    # both lists and dicts are not hashable and we need dep types to be hashable
    return tuple(make_hashable(action) for action in value)


def custom_attrs(
    input: dict[str, Any],  # noqa: A002
    options: dict[str, Any] | None = None,
) -> tuple[frozenset[Any], frozenset[Any] | None]:
    input_wrapped = make_hashable(input)
    options_wrapped = make_hashable(options) if options else None
    return input_wrapped, options_wrapped
