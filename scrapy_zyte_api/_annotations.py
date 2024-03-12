from enum import Enum
from typing import Iterable, List, Optional, TypedDict

import attrs


class ExtractFrom(str, Enum):
    httpResponseBody: str = "httpResponseBody"
    browserHtml: str = "browserHtml"


class Geolocation:
    pass


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


def actions_list(actions: Iterable[Action]):
    # both lists and dicts are not hashable and we need dep types to be hashable
    return tuple(frozenset(action.items()) for action in actions)


@attrs.define
class Actions:
    result: Optional[List[_ActionResult]]
