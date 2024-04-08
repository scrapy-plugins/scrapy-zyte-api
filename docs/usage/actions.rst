.. _actions:

======================
Handling action errors
======================

Even though Zyte API considers a response successful :ref:`even if a browser
action fails <zyte-api-successful-responses>`, scrapy-zyte-api retries such
responses by default. See :ref:`ZYTE_API_ACTION_ERROR_RETRY_ENABLED`.

You can also use :ref:`ZYTE_API_ACTION_ERROR_HANDLING` to determine how such
responses are handled when they are not retried or when retries are exceeded:
treated as a success (default), ignored, or treated as an error.

Action error caching
====================

If you use
:class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`, you might
want to use a custom :setting:`HTTPCACHE_POLICY <scrapy:HTTPCACHE_POLICY>` to
prevent responses with failed actions (i.e. after exceeding retries) to be
cached:

.. code-block:: python
    :caption: myproject/extensions.py

    from scrapy import Request
    from scrapy.extensions.httpcache import DummyPolicy
    from scrapy.http import Response
    from scrapy_zyte_api.responses import ZyteAPIResponse, ZyteAPITextResponse

    class ZyteAPIFailedActionsPolicy(DummyPolicy):

        def should_cache_response(self, response: Response, request: Request):
            if (
                isinstance(response, (ZyteAPIResponse, ZyteAPITextResponse))
                and any("error" in action for action in response.raw_api_response.get("actions", []))
            ):
                return False
            return super().should_cache_response(response, request)

And enable it in your settings:

.. code-block:: python
    :caption: myproject/settings.py

    HTTPCACHE_POLICY = "myproject.extensions.ZyteAPIFailedActionsPolicy"
