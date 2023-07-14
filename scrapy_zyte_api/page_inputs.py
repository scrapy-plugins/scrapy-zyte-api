from typing import Annotated, List, Optional, TypedDict

import attrs


class _Selector(TypedDict, total=False):
    type: str
    value: str
    state: Optional[str]


class _Action(TypedDict, total=False):
    action: str
    url: Optional[str]
    urlPattern: Optional[str]
    urlMatchingOptions: Optional[str]
    selector: Optional[_Selector]
    onError: Optional[str]
    delay: Optional[float]
    timeout: Optional[float]
    id: Optional[str]
    keyword: Optional[str]
    key: Optional[str]
    source: Optional[str]
    options: Optional[dict]


@attrs.define
class _Actions:
    result: Optional[List]


@attrs.define
class _ActionsList:
    value: List[_Action]


def Actions(actions: List[_Action]):
    """
    Add this dependency to your page object to execute Zyte API actions::

        import attrs
        from web_poet import ItemPage, BrowserResponse
        from scrapy_zyte_api.page_inputs import Actions

        @attrs.define
        class MyPage(ItemPage)
            response: BrowserResponse
            actions: Actions([
                {"action": "scrollBottom"},
            ])
            # ...

    """
    return Annotated[_Actions, _ActionsList[actions]]
