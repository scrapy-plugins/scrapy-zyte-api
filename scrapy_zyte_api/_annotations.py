from enum import Enum
from typing import Iterable, List, Optional, TypedDict


class ExtractFrom(str, Enum):
    """:ref:`Annotation <annotations>` to specify the :ref:`extraction source
    <zyte-api-extract-from>` of an automatic extraction :ref:`input <inputs>`,
    such as :class:`~zyte_common_items.Product` or
    :class:`~zyte_common_items.Article`.

    See :ref:`annotations`.
    """

    httpResponseBody: str = "httpResponseBody"
    browserHtml: str = "browserHtml"


class _Selector(TypedDict, total=False):
    type: str
    value: str
    state: Optional[str]


class Action(TypedDict, total=False):
    action: str
    address: Optional[dict]
    args: Optional[dict]
    button: Optional[str]
    delay: Optional[float]
    id: Optional[str]
    key: Optional[str]
    keyword: Optional[str]
    left: Optional[int]
    maxPageHeight: Optional[int]
    maxScrollCount: Optional[int]
    maxScrollDelay: Optional[float]
    onError: Optional[str]
    options: Optional[dict]
    selector: Optional[_Selector]
    source: Optional[str]
    text: Optional[str]
    timeout: Optional[float]
    top: Optional[int]
    url: Optional[str]
    urlMatchingOptions: Optional[str]
    urlPattern: Optional[str]
    values: Optional[List[str]]
    waitForNavigationTimeout: Optional[float]
    waitUntil: Optional[str]


class _ActionResult(TypedDict, total=False):
    action: str
    elapsedTime: float
    status: str
    error: Optional[str]


def make_hashable(obj):
    if isinstance(obj, (tuple, list)):
        return tuple((make_hashable(e) for e in obj))

    if isinstance(obj, dict):
        return frozenset((make_hashable(k), make_hashable(v)) for k, v in obj.items())

    return obj


def actions(value: Iterable[Action]):
    """Convert an iterable of :class:`~scrapy_zyte_api.Action` dicts into a hashable value."""
    # both lists and dicts are not hashable and we need dep types to be hashable
    return tuple(make_hashable(action) for action in value)
