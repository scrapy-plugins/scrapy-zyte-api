import logging
from asyncio import create_task, sleep
from collections import deque
from typing import cast
from uuid import uuid4

from scrapy import Request
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.exceptions import IgnoreRequest
from scrapy.http.request import NO_CALLBACK
from scrapy.utils.defer import deferred_to_future
from scrapy.utils.misc import create_instance, load_object
from zyte_api.aio.errors import RequestError

from ._params import _ParamParser

logger = logging.getLogger(__name__)


_start_requests_processed = object()


class _BaseMiddleware:
    _slot_prefix = "zyte-api@"

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._param_parser = _ParamParser(crawler, cookies_enabled=False)
        self._crawler = crawler

    def slot_request(self, request, spider, force=False):
        if not force and self._param_parser.parse(request) is None:
            return

        downloader = self._crawler.engine.downloader
        slot_id = downloader._get_slot_key(request, spider)
        if not isinstance(slot_id, str) or not slot_id.startswith(self._slot_prefix):
            slot_id = f"{self._slot_prefix}{slot_id}"
            request.meta["download_slot"] = slot_id
        _, slot = downloader._get_slot(request, spider)
        slot.delay = 0


class ScrapyZyteAPIDownloaderMiddleware(_BaseMiddleware):
    def __init__(self, crawler) -> None:
        super().__init__(crawler)
        self._forbidden_domain_start_request_count = 0
        self._total_start_request_count = 0

        self._max_requests = crawler.settings.getint("ZYTE_API_MAX_REQUESTS")
        if self._max_requests:
            logger.info(
                f"Maximum Zyte API requests for this crawl is set at "
                f"{self._max_requests}. The spider will close when it's "
                f"reached."
            )

        crawler.signals.connect(
            self._start_requests_processed, signal=_start_requests_processed
        )

    def _get_spm_mw(self):
        spm_mw_classes = []

        try:
            from scrapy_crawlera import CrawleraMiddleware
        except ImportError:
            pass
        else:
            spm_mw_classes.append(CrawleraMiddleware)

        try:
            from scrapy_zyte_smartproxy import ZyteSmartProxyMiddleware
        except ImportError:
            pass
        else:
            spm_mw_classes.append(ZyteSmartProxyMiddleware)

        middlewares = self._crawler.engine.downloader.middleware.middlewares
        for middleware in middlewares:
            if isinstance(middleware, tuple(spm_mw_classes)):
                return middleware
        return None

    def _check_spm_conflict(self, spider):
        checked = getattr(self, "_checked_spm_conflict", False)
        if checked:
            return
        self._checked_spm_conflict = True
        settings = self._crawler.settings
        in_transparent_mode = settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
        spm_mw = self._get_spm_mw()
        spm_is_enabled = spm_mw and spm_mw.is_enabled(spider)
        if not in_transparent_mode or not spm_is_enabled:
            return
        logger.error(
            "Both scrapy-zyte-smartproxy and the transparent mode of "
            "scrapy-zyte-api are enabled. You should only enable one of "
            "those at the same time.\n"
            "\n"
            "To combine requests that use scrapy-zyte-api and requests "
            "that use scrapy-zyte-smartproxy in the same spider:\n"
            "\n"
            "1. Leave scrapy-zyte-smartproxy enabled.\n"
            "2. Disable the transparent mode of scrapy-zyte-api.\n"
            "3. To send a specific request through Zyte API, use "
            "request.meta to set dont_proxy to True and zyte_api_automap "
            "either to True or to a dictionary of extra request fields."
        )
        from twisted.internet import reactor
        from twisted.internet.interfaces import IReactorCore

        reactor = cast(IReactorCore, reactor)
        reactor.callLater(
            0, self._crawler.engine.close_spider, spider, "plugin_conflict"
        )

    def _start_requests_processed(self, count):
        self._total_start_request_count = count
        self._maybe_close()

    def process_request(self, request, spider):
        self._check_spm_conflict(spider)

        if self._param_parser.parse(request) is None:
            return

        self.slot_request(request, spider, force=True)

        if self._max_requests_reached(self._crawler.engine.downloader):
            self._crawler.engine.close_spider(spider, "closespider_max_zapi_requests")
            raise IgnoreRequest(
                f"The request {request} is skipped as {self._max_requests} max "
                f"Zyte API requests have been reached."
            )

    def _max_requests_reached(self, downloader) -> bool:
        if not self._max_requests:
            return False

        zapi_req_count = self._crawler.stats.get_value("scrapy-zyte-api/processed", 0)
        download_req_count = sum(
            [
                len(slot.transferring)
                for slot_id, slot in downloader.slots.items()
                if slot_id.startswith(self._slot_prefix)
            ]
        )
        total_requests = zapi_req_count + download_req_count
        return total_requests >= self._max_requests

    def process_exception(self, request, exception, spider):
        if (
            not request.meta.get("is_start_request")
            or not isinstance(exception, RequestError)
            or exception.status != 451
        ):
            return

        self._forbidden_domain_start_request_count += 1
        self._maybe_close()

    def _maybe_close(self):
        if not self._total_start_request_count:
            return
        if self._forbidden_domain_start_request_count < self._total_start_request_count:
            return
        logger.error(
            "Stopping the spider, all start requests failed because they "
            "were pointing to a domain forbidden by Zyte API."
        )
        self._crawler.engine.close_spider(
            self._crawler.spider, "failed_forbidden_domain"
        )


class ScrapyZyteAPISpiderMiddleware(_BaseMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        self._send_signal = crawler.signals.send_catch_log

    def process_start_requests(self, start_requests, spider):
        # Mark start requests and reports to the downloader middleware the
        # number of them once all have been processed.
        count = 0
        for request in start_requests:
            request.meta["is_start_request"] = True
            self.slot_request(request, spider)
            yield request
            count += 1
        self._send_signal(_start_requests_processed, count=count)

    def process_spider_output(self, response, result, spider):
        for item_or_request in result:
            if isinstance(item_or_request, Request):
                self.slot_request(item_or_request, spider)
            yield item_or_request

    async def process_spider_output_async(self, response, result, spider):
        async for item_or_request in result:
            if isinstance(item_or_request, Request):
                self.slot_request(item_or_request, spider)
            yield item_or_request


class _DummyChecker:

    def check(self, response):
        return True


_ZYTE_API_META_KEYS = ("zyte_api", "zyte_api_automap", "zyte_api_provider")
_SESSION_INIT_META_KEY = "_is_session_init_request"


class _SessionManager:

    def __init__(self, crawler):
        settings = crawler.settings

        # Scrapy component to check responses to determine whether sessions
        # have expired or not.
        checker = settings.get("ZYTE_API_SESSION_CHECKER", None)
        if checker:
            self._checker = create_instance(
                load_object(checker), settings=None, crawler=crawler
            )
        else:
            self._checker = _DummyChecker()

        # Maximum number of concurrent sessions to use.
        self._max_count = settings.getint("ZYTE_API_SESSION_COUNT", 8)

        # Zyte API parameters for session initialization.
        self._params = settings.getdict("ZYTE_API_SESSION_PARAMS", {})

        # URL to use for session initialization.
        self._url = settings.get("ZYTE_API_SESSION_URL", None)

        self._crawler = crawler

        # The pool contains the IDs of sessions that have not expired yet.
        #
        # While the pool is smaller than the number of desired sessions, for
        # every request needing a session a new session ID is added to the pool
        # and its session initialization starts.
        #
        # Once the pool is full, sessions are picked from the queue, which
        # should contain all pool sessions that have been initialized.
        #
        # As soon as a session expires, it is removed from the pool and
        # replaced with a new session ID, and a task to initialize that new
        # session is started.
        self._pool = set()

        # The queue is a rotating list of session IDs to use.
        #
        # The way to use the queue is to get a session ID with popleft(), and
        # put it back to the end of the queue with append().
        #
        # The queue may contain session IDs from expired sessions. If the
        # popped session ID cannot be found in the pool, then it should be
        # discarded instead of being put back in the queue.
        #
        # When a new session ID is added to the pool, it is still not added to
        # the queue until the session is actually initialized, when it is
        # appended to the queue.
        #
        # If the queue is empty, sleep and try again. Sessions from the pool
        # will be appended to the queue as they are initialized and ready to
        # use.
        self._queue = deque()

        # Contains the on-going tasks to create new sessions.
        #
        # Keeping a reference to those tasks until they are done is necessary
        # to prevent garbage collection to remove the tasks.
        self._init_tasks = set()

    async def _init_session(self, session_id, request):
        url = self._url or request.url
        session_init_request = Request(
            url,
            meta={
                _SESSION_INIT_META_KEY: True,
                "zyte_api": {**self._params, "session": {"id": session_id}},
            },
            callback=NO_CALLBACK,
        )
        deferred = self._crawler.engine.download(session_init_request)
        try:
            response = await deferred_to_future(deferred)
        except Exception:
            return False
        return self._checker.check(session_init_request, response)

    async def _create_session(self, request):
        session_init_succeeded = False
        while not session_init_succeeded:
            session_id = str(uuid4())
            self._pool.add(session_id)
            session_init_succeeded = await self._init_session(session_id, request)
            if not session_init_succeeded:
                self._pool.remove(session_id)
        self._queue.append(session_id)
        return session_id

    async def _next_from_queue(self):
        session_id = None
        while session_id not in self._pool:  # After 1st loop: invalid session.
            try:
                session_id = self._queue.popleft()
            except IndexError:  # No ready-to-use session available.
                await sleep(1)
        self._queue.append(session_id)
        return session_id

    async def _next(self, request):
        """Return the ID of the next working session in the session pool
        rotation.

        *request* is needed to determine the URL to use for request
        initialization if the :setting:`ZYTE_API_SESSION_URL` setting is not
        defined.
        """
        if len(self._pool) < self._max_count:
            session_id = await self._create_session(request)
        else:
            session_id = await self._next_from_queue()
        return session_id

    def _is_session_init_request(self, request):
        """Return ``True`` if the request is one of the requests being used
        to initialize a session, or ``False`` otherwise.

        If ``True`` is returned for a request, the session ID of that request
        should not be modified, or it will break the session management logic.
        """
        return request.meta.get(_SESSION_INIT_META_KEY, False)

    def _get_request_session_id(self, request):
        for meta_key in _ZYTE_API_META_KEYS:
            if meta_key not in request.meta:
                continue
            session_id = request.meta[meta_key].get("session", {}).get("id", None)
            if session_id:
                return session_id
        return None

    def _start_session_refresh(self, session_id, request):
        self._pool.discard(session_id)
        task = create_task(self._create_session(request))
        self._init_tasks.add(task)
        task.add_done_callback(self._init_tasks.discard)

    async def check(self, request, response):
        """Check the response for signs of session expiration, update the
        internal session pool accordingly, and return ``False`` if the session
        has expired or ``True`` if the session passed validation."""
        if self._is_session_init_request(request):
            return True

        passed = self._checker.check(request, response)
        if passed:
            return True

        session_id = self._get_request_session_id(request)
        if session_id is None:
            logger.warning(
                f"Request {request} had no session ID assigned, "
                f"unexpectedly. Please report this issue to the "
                f"scrapy-zyte-api maintainers, providing a minimal, "
                f"reproducible example."
            )
            return True

        self._start_session_refresh(session_id, request)
        return False

    async def assign(self, request):
        """Assign a working session to *request*."""
        if self._is_session_init_request(request):
            return

        session_id = await self._sessions._next(request)
        for meta_key in _ZYTE_API_META_KEYS:
            if meta_key not in request.meta:
                continue
            # Note: If there is a session set already (e.g. a request being
            # retried), it is overridden.
            request.meta[meta_key]["session"] = {"id": session_id}


class ScrapyZyteAPISessionDownloaderMiddleware:

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._sessions = _SessionManager(crawler)

    async def process_request(self, request, spider):
        await self._sessions.assign(request)

    async def process_response(self, request, response, spider):
        passed = await self._sessions.check(request, response)
        if not passed:
            new_request_or_none = get_retry_request(
                request,
                spider=spider,
                reason="session_expired",
            )
            if not new_request_or_none:
                raise IgnoreRequest
            return new_request_or_none
