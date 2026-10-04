from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy import Request


def is_manual_request(request: Request) -> bool:
    return request.meta.get("zyte_api") not in (None, False)
