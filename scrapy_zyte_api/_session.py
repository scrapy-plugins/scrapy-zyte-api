from asyncio import create_task, sleep
from collections import defaultdict, deque
from copy import deepcopy
from logging import getLogger
from typing import Any, Deque, Dict, Optional, Set, Type, TypeVar, Union, cast
from uuid import uuid4

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.python import global_object_name
from url_matcher import Patterns
from web_poet import ApplyRule
from web_poet.rules import Strings
from zyte_api import RequestError

logger = getLogger(__name__)
SESSION_INIT_META_KEY = "_is_session_init_request"
ZYTE_API_META_KEYS = ("zyte_api", "zyte_api_automap", "zyte_api_provider")

try:
    from scrapy_poet import DummyResponse
except ImportError:

    class DummyResponse:  # type: ignore[no-redef]
        pass


try:
    from scrapy.downloadermiddlewares.retry import get_retry_request
except ImportError:
    # https://github.com/scrapy/scrapy/blob/b1fe97dc6c8509d58b29c61cf7801eeee1b409a9/scrapy/downloadermiddlewares/retry.py#L57-L142
    def get_retry_request(
        request,
        *,
        spider,
        reason="unspecified",
        max_retry_times=None,
        priority_adjust=None,
        stats_base_key="retry",
    ):
        settings = spider.crawler.settings
        assert spider.crawler.stats
        stats = spider.crawler.stats
        retry_times = request.meta.get("retry_times", 0) + 1
        if max_retry_times is None:
            max_retry_times = request.meta.get("max_retry_times")
            if max_retry_times is None:
                max_retry_times = settings.getint("RETRY_TIMES")
        if retry_times <= max_retry_times:
            logger.debug(
                "Retrying %(request)s (failed %(retry_times)d times): %(reason)s",
                {"request": request, "retry_times": retry_times, "reason": reason},
                extra={"spider": spider},
            )
            new_request: Request = request.copy()
            new_request.meta["retry_times"] = retry_times
            new_request.dont_filter = True
            if priority_adjust is None:
                priority_adjust = settings.getint("RETRY_PRIORITY_ADJUST")
            new_request.priority = request.priority + priority_adjust

            if callable(reason):
                reason = reason()
            if isinstance(reason, Exception):
                reason = global_object_name(reason.__class__)

            stats.inc_value(f"{stats_base_key}/count")
            stats.inc_value(f"{stats_base_key}/reason_count/{reason}")
            return new_request
        stats.inc_value(f"{stats_base_key}/max_reached")
        logger.error(
            "Gave up retrying %(request)s (failed %(retry_times)d times): "
            "%(reason)s",
            {"request": request, "retry_times": retry_times, "reason": reason},
            extra={"spider": spider},
        )
        return None


try:
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = "parse"

try:
    from scrapy.utils.defer import deferred_to_future
except ImportError:
    import asyncio
    from warnings import catch_warnings, filterwarnings

    # https://github.com/scrapy/scrapy/blob/b1fe97dc6c8509d58b29c61cf7801eeee1b409a9/scrapy/utils/reactor.py#L119-L147
    def set_asyncio_event_loop():
        try:
            with catch_warnings():
                # In Python 3.10.9, 3.11.1, 3.12 and 3.13, a DeprecationWarning
                # is emitted about the lack of a current event loop, because in
                # Python 3.14 and later `get_event_loop` will raise a
                # RuntimeError in that event. Because our code is already
                # prepared for that future behavior, we ignore the deprecation
                # warning.
                filterwarnings(
                    "ignore",
                    message="There is no current event loop",
                    category=DeprecationWarning,
                )
                event_loop = asyncio.get_event_loop()
        except RuntimeError:
            # `get_event_loop` raises RuntimeError when called with no asyncio
            # event loop yet installed in the following scenarios:
            # - Previsibly on Python 3.14 and later.
            #   https://github.com/python/cpython/issues/100160#issuecomment-1345581902
            event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(event_loop)
        return event_loop

    # https://github.com/scrapy/scrapy/blob/b1fe97dc6c8509d58b29c61cf7801eeee1b409a9/scrapy/utils/reactor.py#L115-L116
    def _get_asyncio_event_loop():
        return set_asyncio_event_loop()

    # https://github.com/scrapy/scrapy/blob/b1fe97dc6c8509d58b29c61cf7801eeee1b409a9/scrapy/utils/defer.py#L360-L379
    def deferred_to_future(d):
        return d.asFuture(_get_asyncio_event_loop())


try:
    from scrapy.utils.misc import build_from_crawler
except ImportError:
    T = TypeVar("T")

    def build_from_crawler(
        objcls: Type[T], crawler: Crawler, /, *args: Any, **kwargs: Any
    ) -> T:
        return create_instance(objcls, settings=None, crawler=crawler, *args, **kwargs)


class DefaultChecker:

    def check(self, response: Response, request: Request):
        return True


class TooManyBadSessionInits(RuntimeError):
    pass


class SessionConfig:

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self.crawler = crawler

        settings = crawler.settings
        self._fallback_location = settings.getdict("ZYTE_API_SESSION_LOCATION")
        self._fallback_params = settings.getdict("ZYTE_API_SESSION_PARAMS")

        checker_cls = settings.get("ZYTE_API_SESSION_CHECKER", None)
        if checker_cls:
            checker = build_from_crawler(load_object(checker_cls), crawler)
        else:
            checker = DefaultChecker()
        self.check = checker.check

    def pool(self, request: Request) -> str:
        return urlparse_cached(request).netloc

    def location(self, request: Request) -> Dict[str, str]:
        return request.meta.get("zyte_api_session_location") or self._fallback_location

    def params(self, request: Request) -> Optional[Dict[str, str]]:
        location = self.location(request)
        params = request.meta.get("zyte_api_session_params") or self._fallback_params
        if not location:
            return params
        return {
            "url": params.get("url", request.url),
            "browserHtml": True,
            "actions": [
                {
                    "action": "setLocation",
                    "address": location,
                }
            ],
        }


try:
    from web_poet import RulesRegistry
except ImportError:

    class SessionConfigRulesRegistry:

        def session_config_cls(self, request: Request) -> Type[SessionConfig]:
            return SessionConfig

        def session_config(
            self,
            include: Strings,
            *,
            instead_of: Optional[Type] = SessionConfig,
            exclude: Optional[Strings] = None,
            priority: int = 500,
            **kwargs,
        ):
            raise RuntimeError(
                "To use the @session_config decorator you first must install "
                "web-poet."
            )

else:

    class SessionConfigRulesRegistry(RulesRegistry):

        def __init__(self):
            rules = [ApplyRule(for_patterns=Patterns(include=[""]), use=SessionConfig)]
            super().__init__(rules=rules)

        def session_config_cls(self, request: Request) -> Type[SessionConfig]:
            cls = SessionConfig
            overrides = self.overrides_for(request.url)
            while cls in overrides:
                cls = overrides[cls]
            return cls

        def session_config(
            self,
            include: Strings,
            *,
            instead_of: Optional[Type[SessionConfig]] = SessionConfig,
            exclude: Optional[Strings] = None,
            priority: int = 500,
            **kwargs,
        ):
            return self.handle_urls(
                include=include,
                instead_of=instead_of,
                exclude=exclude,
                priority=priority,
                **kwargs,
            )


session_config_registry = SessionConfigRulesRegistry()
session_config = session_config_registry.session_config


class _SessionManager:

    def __init__(self, crawler: Crawler):
        self._crawler = crawler

        settings = crawler.settings

        pool_size = settings.getint("ZYTE_API_SESSION_POOL_SIZE", 8)
        self._pending_initial_sessions = defaultdict(lambda: pool_size)
        pool_sizes = settings.getdict("ZYTE_API_SESSION_POOL_SIZES", {})
        for pool, size in pool_sizes.items():
            self._pending_initial_sessions[pool] = size

        self._max_errors = settings.getdict("ZYTE_API_SESSION_MAX_ERRORS", 1)
        self._errors = defaultdict(int)

        max_bad_inits = settings.getint("ZYTE_API_SESSION_MAX_BAD_INITS", 8)
        self._max_bad_inits = defaultdict(lambda: max_bad_inits)
        max_bad_inits_per_pool = settings.getdict(
            "ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL", {}
        )
        for pool, pool_max_bad_inits in max_bad_inits_per_pool.items():
            self._max_bad_inits[pool] = pool_max_bad_inits
        self._bad_inits = defaultdict(int)

        # Transparent mode, needed to determine whether to set the session
        # using ``zyte_api`` or ``zyte_api_automap``.
        self._transparent_mode: bool = settings.getbool(
            "ZYTE_API_TRANSPARENT_MODE", False
        )

        # Each pool contains the IDs of sessions that have not expired yet.
        #
        # While the initial sessions of a pool have not all been started, for
        # every request needing a session, a new session is initialized and
        # then added to the pool.
        #
        # Once a pool is full, sessions are picked from the pool queue, which
        # should contain all pool sessions that have been initialized.
        #
        # As soon as a session expires, it is removed from its pool, and a task
        # to initialize that new session is started.
        self._pools: Dict[str, Set[str]] = defaultdict(set)

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
        self._queues: Dict[str, Deque[str]] = defaultdict(deque)

        # Contains the on-going tasks to create new sessions.
        #
        # Keeping a reference to those tasks until they are done is necessary
        # to prevent garbage collection to remove the tasks.
        self._init_tasks = set()

        self._warn_on_no_body = settings.getbool(
            "ZYTE_API_SESSION_CHECKER_WARN_ON_NO_BODY", True
        )

        self._session_config_map = {}

    def _get_session_config(self, request: Request) -> SessionConfig:
        cls = session_config_registry.session_config_cls(request)
        if cls not in self._session_config_map:
            self._session_config_map[cls] = build_from_crawler(cls, self._crawler)
        return self._session_config_map[cls]

    async def _init_session(self, session_id: str, request: Request) -> bool:
        session_config = self._get_session_config(request)
        pool = session_config.pool(request)

        session_params = deepcopy(session_config.params(request))
        session_init_url = session_params.pop("url", request.url)
        session_init_request = Request(
            session_init_url,
            meta={
                SESSION_INIT_META_KEY: True,
                "zyte_api": {**session_params, "session": {"id": session_id}},
            },
            callback=NO_CALLBACK,
        )
        deferred = self._crawler.engine.download(session_init_request)
        try:
            response = await deferred_to_future(deferred)
        except Exception:
            self._crawler.stats.inc_value(
                f"scrapy-zyte-api/sessions/pools/{pool}/init/failed"
            )
            result = False
        else:
            result = session_config.check(response, session_init_request)
            outcome = "passed" if result else "failed"
            self._crawler.stats.inc_value(
                f"scrapy-zyte-api/sessions/pools/{pool}/init/check-{outcome}"
            )
        return result

    async def _create_session(self, request: Request) -> str:
        session_config = self._get_session_config(request)
        pool = session_config.pool(request)
        while True:
            session_id = str(uuid4())
            session_init_succeeded = await self._init_session(session_id, request)
            if session_init_succeeded:
                self._pools[pool].add(session_id)
                self._bad_inits[pool] = 0
                break
            self._bad_inits[pool] += 1
            if self._bad_inits[pool] >= self._max_bad_inits[pool]:
                raise TooManyBadSessionInits
        self._queues[pool].append(session_id)
        return session_id

    async def _next_from_queue(self, request: Request) -> str:
        session_id = None
        session_config = self._get_session_config(request)
        pool = session_config.pool(request)
        while session_id not in self._pools[pool]:  # After 1st loop: invalid session.
            try:
                session_id = self._queues[pool].popleft()
            except IndexError:  # No ready-to-use session available.
                await sleep(1)
        assert session_id is not None
        self._queues[pool].append(session_id)
        return session_id

    async def _next(self, request) -> str:
        """Return the ID of the next working session in the session pool
        rotation.

        *request* is needed to determine the URL to use for request
        initialization.
        """
        session_config = self._get_session_config(request)
        pool = session_config.pool(request)
        if self._pending_initial_sessions[pool] >= 1:
            self._pending_initial_sessions[pool] -= 1
            session_id = await self._create_session(request)
        else:
            session_id = await self._next_from_queue(request)
        return session_id

    def is_init_request(self, request: Request) -> bool:
        """Return ``True`` if the request is one of the requests being used
        to initialize a session, or ``False`` otherwise.

        If ``True`` is returned for a request, the session ID of that request
        should not be modified, or it will break the session management logic.
        """
        return request.meta.get(SESSION_INIT_META_KEY, False)

    def _get_request_session_id(self, request: Request) -> Optional[str]:
        for meta_key in ZYTE_API_META_KEYS:
            if meta_key not in request.meta:
                continue
            session_id = request.meta[meta_key].get("session", {}).get("id", None)
            if session_id:
                return session_id
        return None

    def _start_session_refresh(self, session_id: str, request: Request) -> bool:
        session_config = self._get_session_config(request)
        pool = session_config.pool(request)
        try:
            self._pools[pool].remove(session_id)
        except KeyError:
            # More than 1 request was using the same session concurrently. Do
            # not refresh the session again.
            pass
        else:
            task = create_task(self._create_session(request))
            self._init_tasks.add(task)
            task.add_done_callback(self._init_tasks.discard)
        try:
            del self._errors[session_id]
        except KeyError:
            pass

    def _start_request_session_refresh(self, request: Request) -> bool:
        session_id = self._get_request_session_id(request)
        if session_id is None:
            logger.warning(
                f"Request {request} had no session ID assigned, "
                f"unexpectedly. Please report this issue to the "
                f"scrapy-zyte-api maintainers, providing a minimal, "
                f"reproducible example."
            )
            return
        self._start_session_refresh(session_id, request)

    async def check(self, response: Response, request: Request) -> bool:
        """Check the response for signs of session expiration, update the
        internal session pool accordingly, and return ``False`` if the session
        has expired or ``True`` if the session passed validation."""
        session_config = self._get_session_config(request)
        passed = session_config.check(response, request)
        pool = session_config.pool(request)
        outcome = "passed" if passed else "failed"
        self._crawler.stats.inc_value(
            f"scrapy-zyte-api/sessions/pools/{pool}/use/check-{outcome}"
        )
        if passed:
            return True
        if (
            self._warn_on_no_body
            and not response.body
            and "httpResponseBody" not in response.raw_api_response
            and "browserHtml" not in response.raw_api_response
        ):
            logger.warning(
                f"Validation failed for {response}, which lacks both "
                f"httpResponseBody and browserHtml. Does your session "
                f"checking code rely on inspecting the response body? If not, "
                f"set ZYTE_API_SESSION_CHECKER_WARN_ON_NO_BODY to False to "
                f"silence this warning."
            )
        self._start_request_session_refresh(request)
        return False

    async def assign(self, request: Request):
        """Assign a working session to *request*."""
        session_id = await self._next(request)
        # Note: If there is a session set already (e.g. a request being
        # retried), it is overridden.
        request.meta.setdefault("zyte_api_provider", {})["session"] = {"id": session_id}
        if (
            "zyte_api" in request.meta
            or request.meta.get("zyte_api_automap", None) is False
            or (
                "zyte_api_automap" not in request.meta
                and self._transparent_mode is False
            )
        ):
            meta_key = "zyte_api"
        else:
            meta_key = "zyte_api_automap"
        request.meta.setdefault(meta_key, {})["session"] = {"id": session_id}

    def handle_error(self, request: Request):
        session_config = self._get_session_config(request)
        pool = session_config.pool(request)
        self._crawler.stats.inc_value(
            f"scrapy-zyte-api/sessions/pools/{pool}/use/failed"
        )
        session_id = self._get_request_session_id(request)
        self._errors[session_id] += 1
        if self._errors[session_id] < self._max_errors:
            return
        self._sessions._start_request_session_refresh(request)


class ScrapyZyteAPISessionDownloaderMiddleware:

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        return cls(crawler)

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("ZYTE_API_SESSION_ENABLED", False):
            raise NotConfigured
        self._crawler = crawler
        self._sessions = _SessionManager(crawler)

    async def process_request(self, request: Request, spider: Spider) -> None:
        if self._sessions.is_init_request(request):
            return
        try:
            await self._sessions.assign(request)
        except TooManyBadSessionInits:
            from twisted.internet import reactor
            from twisted.internet.interfaces import IReactorCore

            reactor = cast(IReactorCore, reactor)
            reactor.callLater(
                0, self._crawler.engine.close_spider, spider, "bad_session_inits"
            )

    async def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response, None]:
        if isinstance(response, DummyResponse) or self._sessions.is_init_request(
            request
        ):
            return response
        passed = await self._sessions.check(response, request)
        if not passed:
            new_request_or_none = get_retry_request(
                request,
                spider=spider,
                reason="session_expired",
            )
            if not new_request_or_none:
                raise IgnoreRequest
            return new_request_or_none
        return response

    def process_exception(
        self, request: Request, exception: Exception, spider: Spider
    ) -> Union[Request, None]:
        if not isinstance(exception, RequestError) or self._sessions.is_init_request(
            request
        ):
            return

        self._sessions.handle_error(request)
        return get_retry_request(
            request,
            spider=spider,
            reason="unsuccessful_response",
        )
