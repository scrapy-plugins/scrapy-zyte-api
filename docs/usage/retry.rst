.. _retry:

Retries
=======

API requests are retried automatically using the default retry policy of
:doc:`python-zyte-api <python-zyte-api:index>`.

API requests that exceed retries are dropped. You cannot manage API request
retries through :ref:`downloader middlewares <topics-downloader-middleware>`.

Use the :setting:`ZYTE_API_RETRY_POLICY` setting or the
:reqmeta:`zyte_api_retry_policy`
:attr:`Request.meta <scrapy.http.Request.meta>` key to override the default
retry policy with a custom retry policy.

For example, to increase the maximum number of retries to 10 before dropping
the API request, you can subclass :class:`~zyte_api.aio.retry.RetryFactory` as
follows:

.. code-block:: python

    # project/retry_policies.py
    from tenacity import stop_after_attempt
    from zyte_api.aio.retry import RetryFactory


    class CustomRetryFactory(RetryFactory):
        temporary_download_error_stop = stop_after_attempt(10)


    CUSTOM_RETRY_POLICY = CustomRetryFactory().build()

    # project/settings.py
    ZYTE_API_RETRY_POLICY = "project.retry_policies.CUSTOM_RETRY_POLICY"


To extend this retry policy, so it will also retry HTTP 521 errors, the same
as HTTP 520 errors, you can implement:

.. code-block:: python

    # project/retry_policies.py
    from tenacity import retry_if_exception, RetryCallState, stop_after_attempt
    from zyte_api.aio.errors import RequestError
    from zyte_api.aio.retry import RetryFactory


    def is_http_521(exc: BaseException) -> bool:
        return isinstance(exc, RequestError) and exc.status == 521


    class CustomRetryFactory(RetryFactory):

        retry_condition = RetryFactory.retry_condition | retry_if_exception(is_http_521)
        temporary_download_error_stop = stop_after_attempt(10)

        def wait(self, retry_state: RetryCallState) -> float:
            if is_http_521(retry_state.outcome.exception()):
                return self.temporary_download_error_wait(retry_state=retry_state)
            return super().wait(retry_state)

        def stop(self, retry_state: RetryCallState) -> bool:
            if is_http_521(retry_state.outcome.exception()):
                return self.temporary_download_error_stop(retry_state)
            return super().stop(retry_state)


    CUSTOM_RETRY_POLICY = CustomRetryFactory().build()

    # project/settings.py
    ZYTE_API_RETRY_POLICY = "project.retry_policies.CUSTOM_RETRY_POLICY"
