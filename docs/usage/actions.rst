.. _actions:

======================
Handling action errors
======================

Zyte API responses are considered successful :ref:`even if some browser actions
fail <zyte-api-successful-responses>`.

If you wish to retry requests whose response contains actions that failed, you
can define a custom Scrapy middleware as follows:

.. code-block:: python
    :caption: myproject/middlewares.py

    from scrapy import Request, Spider
    from scrapy.http import Response
    from scrapy.downloadermiddlewares.retry import get_retry_request
    from scrapy.settings import BaseSettings
    from scrapy_zyte_api.responses import ZyteAPIResponse, ZyteAPITextResponse

    class ZyteAPIFailedActionsRetryMiddleware:

        def __init__(self, settings: BaseSettings):
            if not settings.getbool("RETRY_ENABLED"):
                raise NotConfigured
            self.max_retry_times = settings.getint("RETRY_TIMES")
            self.priority_adjust = settings.getint("RETRY_PRIORITY_ADJUST")

        def process_response(
            self, request: Request, response: Response, spider: Spider
        ) -> Union[Request, Response]:
            if not isinstance(response, (ZyteAPIResponse, ZyteAPITextResponse)):
                return response
            if request.meta.get("dont_retry", False):
                return response
            if any("error" in action for action in response.raw_api_response["actions"]):
                reason = "An action failed"
                new_request = self._retry(request, reason, spider)
                if new_request:
                    return new_request
                else:
                    return response
                    # Note: If you prefer requests that exceed all retries to
                    # be dropped, raise scrapy.exceptions.IgnoreRequest here,
                    # instead of returning the response.
            return response

        def _retry(
            self,
            request: Request,
            reason: Union[str, Exception, Type[Exception]],
            spider: Spider,
        ) -> Optional[Request]:
            max_retry_times = request.meta.get("max_retry_times", self.max_retry_times)
            priority_adjust = request.meta.get("priority_adjust", self.priority_adjust)
            return get_retry_request(
                request,
                reason=reason,
                spider=spider,
                max_retry_times=max_retry_times,
                priority_adjust=priority_adjust,
            )

And enable it in your settings:

.. code-block:: python
    :caption: myproject/settings.py


    DOWNLOADER_MIDDLEWARES = {
        "myproject.middlewares.ZyteAPIFailedActionsRetryMiddleware": 525,
    }

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
                and any("error" in action for action in response.raw_api_response["actions"])
            ):
                return False
            return super().should_cache_response(response, request)

And enable it in your settings:

.. code-block:: python
    :caption: myproject/settings.py


    HTTPCACHE_POLICY = "myproject.extensions.ZyteAPIFailedActionsPolicy"
