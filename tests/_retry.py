from tenacity import wait_none
from zyte_api import RetryFactory

from scrapy_zyte_api._session import SessionRetryFactory


class _NoWaitRetryFactory(RetryFactory):
    """Retry policy that retries as many times as the default one, but without
    waiting between attempts, so that tests that trigger a retry do not spend
    minutes sleeping.

    Only the waits whose stop condition is count-based are zeroed. The
    throttling and network error stop conditions are time-based, so zeroing
    their waits would turn a retry into a tight loop.
    """

    download_error_wait = wait_none()  # python-zyte-api >= 0.7.0
    temporary_download_error_wait = wait_none()  # python-zyte-api < 0.7.0
    undocumented_error_wait = wait_none()


class _NoWaitSessionRetryFactory(_NoWaitRetryFactory, SessionRetryFactory):
    pass


POLICY = _NoWaitRetryFactory().build()
SESSION_POLICY = _NoWaitSessionRetryFactory().build()
