from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.extensions.httpcache import DummyPolicy

from .responses import _has_action_error

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.http import Response


class ScrapyZyteAPIHttpCachePolicy(DummyPolicy):
    """:setting:`HTTPCACHE_POLICY <scrapy:HTTPCACHE_POLICY>` that never caches
    Zyte API responses in which a browser action failed.

    See :ref:`action-error-caching`.
    """

    def should_cache_response(self, response: Response, request: Request) -> bool:
        if _has_action_error(response):
            return False
        return super().should_cache_response(response, request)
