import json
from asyncio import Task, create_task, sleep
from collections import defaultdict, deque
from copy import deepcopy
from functools import partial
from logging import getLogger
from typing import Any, DefaultDict, Deque, Dict, List, Optional, Set, Type, Union, cast
from uuid import uuid4
from weakref import WeakKeyDictionary

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.python import global_object_name
from tenacity import stop_after_attempt
from zyte_api import RequestError, RetryFactory

from .utils import _DOWNLOAD_NEEDS_SPIDER, _build_from_crawler

logger = getLogger(__name__)
SESSION_INIT_META_KEY = "_is_session_init_request"
ZYTE_API_META_KEYS = ("zyte_api", "zyte_api_automap", "zyte_api_provider")


def is_session_init_request(request):
    """Return ``True`` if the request is a :ref:`session initialization request
    <session-init>` or ``False`` otherwise."""
    return request.meta.get(SESSION_INIT_META_KEY, False) is True


class SessionRetryFactory(RetryFactory):
    temporary_download_error_stop = stop_after_attempt(1)


SESSION_DEFAULT_RETRY_POLICY = SessionRetryFactory().build()

try:
    from zyte_api import AggressiveRetryFactory, stop_on_count
except ImportError:
    SESSION_AGGRESSIVE_RETRY_POLICY = SESSION_DEFAULT_RETRY_POLICY
else:

    class AggressiveSessionRetryFactory(AggressiveRetryFactory):
        download_error_stop = stop_on_count(1)

    SESSION_AGGRESSIVE_RETRY_POLICY = AggressiveSessionRetryFactory().build()


try:
    from scrapy_poet import DummyResponse
except ImportError:

    class DummyResponse:  # type: ignore[no-redef]
        pass


try:
    from scrapy.downloadermiddlewares.retry import get_retry_request
except ImportError:  # pragma: no cover
    # https://github.com/scrapy/scrapy/blob/b1fe97dc6c8509d58b29c61cf7801eeee1b409a9/scrapy/downloadermiddlewares/retry.py#L57-L142
    def get_retry_request(  # type: ignore[misc]
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

    def NO_CALLBACK(response):  # type: ignore[misc]
        pass  # pragma: no cover


try:
    from scrapy.utils.defer import deferred_to_future
except ImportError:  # pragma: no cover
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
    def deferred_to_future(d):  # type: ignore[misc]
        return d.asFuture(_get_asyncio_event_loop())


class PoolError(ValueError):
    pass


class TooManyBadSessionInits(RuntimeError):
    pass


class SessionConfig:
    """Default session configuration for :ref:`scrapy-zyte-api sessions
    <session>`."""

    #: List of address fields to use when available, and their order, when
    #: :ref:`creating a pool ID for a request <session-pools>` based on the
    #: content of the :reqmeta:`zyte_api_session_location` metadata key. See
    #: :meth:`pool`.
    ADDRESS_FIELDS: List[str] = [
        "addressCountry",
        "addressRegion",
        "postalCode",
        "streetAddress",
    ]

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self.crawler = crawler

        settings = crawler.settings
        self._setting_location = settings.getdict("ZYTE_API_SESSION_LOCATION")
        self._setting_params = settings.getdict("ZYTE_API_SESSION_PARAMS")

        checker_cls = settings.get("ZYTE_API_SESSION_CHECKER", None)
        if checker_cls:
            self._checker = _build_from_crawler(load_object(checker_cls), crawler)
        else:
            self._checker = None
        self._enabled = crawler.settings.getbool("ZYTE_API_SESSION_ENABLED", False)
        self._pool_counters = defaultdict(int)
        self._param_pools: DefaultDict[str, Dict[str, int]] = defaultdict(dict)

    def enabled(self, request: Request) -> bool:
        """Return ``True`` if the request should use sessions from
        :ref:`session management <session>` or ``False`` otherwise.

        The default implementation is based on settings and request metadata
        keys as described in :ref:`enable-sessions`.
        """
        return request.meta.get("zyte_api_session_enabled", self._enabled)

    def pool(self, request: Request) -> str:
        """Return the ID of the session pool to use for *request*.

        The main aspects of the default implementation are described in
        :ref:`session-pools`.

        When the :reqmeta:`zyte_api_session_params` request metadata key is
        used, the pool ID is the target domain followed by an integer between
        brackets (e.g. ``example.com[0]``), and a log message indicates which
        session initialization parameters are associated with that pool ID.

        When the :reqmeta:`zyte_api_session_location` request metadata key is
        used, the pool ID is the target domain followed by an at sign and the
        comma-separated values of the non-empty fields from
        :data:`ADDRESS_FIELDS` (e.g. ``example.com@US,NY,10001``).
        """
        meta_pool = request.meta.get("zyte_api_session_pool", "")
        if meta_pool:
            return meta_pool
        netloc = urlparse_cached(request).netloc
        meta_params = request.meta.get("zyte_api_session_params", None)
        if meta_params:
            param_key = json.dumps(meta_params, sort_keys=True)
            try:
                index = self._param_pools[netloc][param_key]
            except KeyError:
                index = self._pool_counters[netloc]
                logger.info(
                    f"Session pool {netloc}[{index}] uses these session "
                    f"initialization parameters: {meta_params}"
                )
                self._pool_counters[netloc] += 1
                self._param_pools[netloc][param_key] = index
            return f"{netloc}[{index}]"
        meta_location = request.meta.get("zyte_api_session_location", None)
        if meta_location:
            location_id = ",".join(
                [meta_location[k] for k in self.ADDRESS_FIELDS if k in meta_location]
            )
            return f"{netloc}@{location_id}"
        return netloc

    def location(self, request: Request) -> Dict[str, str]:
        """Return the address :class:`dict` to use for location-based session
        initialization for *request*.

        The default implementation is based on settings and request metadata
        keys as described in :ref:`session-init`.

        When overriding this method, you should only return a custom value if
        the default implementation returns an empty :class:`dict`, e.g.

        .. code-block:: python

            def location(self, request: Request) -> Dict[str, str]:
                fallback = {"addressCountry": "US", "addressRegion": "NY", "postalCode": "10001"}
                return super().location(request) or fallback

        .. note:: An implementation of
            :meth:`~scrapy_zyte_api.SessionConfig.location` can technically
            override :reqmeta:`zyte_api_session_location` or
            :setting:`ZYTE_API_SESSION_LOCATION`, but it is not recommended as
            it breaks the :ref:`precedence chain that users expect
            <session-init>`.

        You should only override this method if you need a location to be
        used even when no location is specified through request metadata or
        settings. It can be specially useful if you can determine the right
        location to use based on the request, e.g.

        .. code-block:: python

            def location(self, request: Request) -> Dict[str, str]:
                fallback = {}
                if postal_code := w3lib.url.url_query_parameter(request.url, "postalCode"):
                    fallback["postalCode"] = postal_code
                return super().location(request) or fallback

        Same as with :reqmeta:`zyte_api_session_location` and
        :setting:`ZYTE_API_SESSION_LOCATION`, the returned location fields
        should match those of the ``address`` parameter of the ``setLocation``
        :http:`action <request:actions>` where possible, even when using an
        implementation of :meth:`params` that does not rely on the
        ``setLocation`` action.
        """
        return request.meta.get("zyte_api_session_location", self._setting_location)

    def params(self, request: Request) -> Dict[str, Any]:
        """Return the Zyte API request parameters to use to initialize a
        session for *request*.

        The default implementation is based on settings and request metadata
        keys as described in :ref:`session-init`.

        When overriding this method, you should return parameters for the
        target location, i.e. the output of :meth:`location`, unless that
        output is an empty :class:`dict`, e.g.

        .. code-block:: python

            def params(self, request: Request) -> Dict[str, Any]:
                if location := self.location(request):
                    return {
                        "url": "https://example.com/new-session/for-country",
                        "httpResponseBody": True,
                        "httpRequestMethod": "POST",
                        "httpRequestText": location["addressCountry"],
                    }
                return {
                    "url": "https://example.com/new-session",
                    "httpResponseBody": True,
                }

        The returned parameters do not need to include :http:`request:url`. If
        missing, it is picked from the request :ref:`triggering a session
        initialization request <pool-size>`.

        .. seealso:: :class:`~scrapy_zyte_api.LocationSessionConfig`
        """
        if location := self.location(request):
            return {
                "browserHtml": True,
                "actions": [
                    {
                        "action": "setLocation",
                        "address": location,
                    }
                ],
            }
        return {"browserHtml": True}

    def check(self, response: Response, request: Request) -> bool:
        """Return ``True`` if the session used to fetch *response* should be
        kept, return ``False`` if it should be discarded, or raise
        :exc:`~scrapy.exceptions.CloseSpider` if the spider should be closed.

        The default implementation checks the outcome of the ``setLocation``
        action if a location was defined, as described in :ref:`session-check`.

        If you need to tell whether *request* is a :ref:`session initialization
        request <session-init>` or not, use
        :func:`~scrapy_zyte_api.is_session_init_request`.

        .. seealso:: :class:`~scrapy_zyte_api.LocationSessionConfig`
        """
        if self._checker:
            return self._checker.check(response, request)
        location = self.location(request)
        if not location:
            return True
        for action in response.raw_api_response.get("actions", []):  # type: ignore[attr-defined]
            if action.get("action", None) != "setLocation":
                continue
            if action.get("error", "").startswith("Action setLocation not supported "):
                logger.error(
                    f"Stopping the spider, tried to use the setLocation "
                    f"action on an unsupported website "
                    f"({urlparse_cached(request).netloc})."
                )
                raise CloseSpider("unsupported_set_location")
            return action.get("status", None) == "success"
        return True


try:
    from web_poet import RulesRegistry
except ImportError:

    class SessionConfigRulesRegistry:

        def session_config_cls(self, request: Request) -> Type[SessionConfig]:
            return SessionConfig

        def session_config(
            self,
            include,
            *,
            instead_of: Optional[Type] = SessionConfig,
            exclude=None,
            priority: int = 500,
            **kwargs,
        ):
            """Mark the decorated :class:`SessionConfig` subclass as the
            :ref:`session config <session-configs>` to use for the specified
            URL patterns.

            Usage example:

            .. code-block:: python

                from typing import Any, Dict

                from scrapy import Request
                from scrapy.http.response import Response
                from scrapy_zyte_api import SessionConfig, session_config


                @session_config(["ecommerce.de.example, ecommerce.us.example"])
                class EcommerceExampleSessionConfig(SessionConfig):

                    def pool(self, request: Request) -> str:
                        return "ecommerce.example"

                    def params(self, request: Request) -> Dict[str, Any]:
                        if location := self.location(request):
                            return {
                                "url": request.url,
                                "browserHtml": True,
                                "actions": [
                                    {
                                        "action": "type",
                                        "selector": {"type": "css", "value": ".zipcode"},
                                        "text": location["postalCode"],
                                    },
                                    {
                                        "action": "click",
                                        "selector": {"type": "css", "value": "[type='submit']"},
                                    },
                                ],
                            }
                        return super().params(request)

                    def check(self, response: Response, request: Request) -> bool:
                        if location := self.location(request):
                            return response.css(".zipcode::text").get() == location["postalCode"]
                        return super().check(response, request)

            Your :class:`~scrapy_zyte_api.SessionConfig` subclass must be
            defined in a module that gets imported at run time. See
            ``SCRAPY_POET_DISCOVER`` in the :ref:`scrapy-poet setting reference
            <scrapy-poet:settings>`.

            The parameters of this decorator are those of
            :func:`web_poet.handle_urls`, only *instead_of* is
            :class:`SessionConfig` by default, *to_return* is not supported,
            and session configs are registered in their own rule registry.
            """
            raise RuntimeError(
                "To use the @session_config decorator you first must install "
                "web-poet."
            )

else:
    from url_matcher import Patterns
    from web_poet import ApplyRule
    from web_poet.rules import Strings

    class SessionConfigRulesRegistry(RulesRegistry):  # type: ignore[no-redef]

        def __init__(self):
            rules = [ApplyRule(for_patterns=Patterns(include=[""]), use=SessionConfig)]  # type: ignore[arg-type]
            super().__init__(rules=rules)

        def session_config_cls(self, request: Request) -> Type[SessionConfig]:
            cls = SessionConfig
            overrides: Dict[Type[SessionConfig], Type[SessionConfig]] = self.overrides_for(request.url)  # type: ignore[assignment]
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
                instead_of=instead_of,  # type: ignore[arg-type]
                exclude=exclude,
                priority=priority,
                **kwargs,
            )


class FatalErrorHandler:

    def __init__(self, crawler):
        self.crawler = crawler

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            return
        from twisted.internet import reactor
        from twisted.internet.interfaces import IReactorCore

        reactor = cast(IReactorCore, reactor)
        close = partial(
            reactor.callLater, 0, self.crawler.engine.close_spider, self.crawler.spider
        )
        if issubclass(exc_type, TooManyBadSessionInits):
            close("bad_session_inits")
        elif issubclass(exc_type, PoolError):
            close("pool_error")
        elif issubclass(exc_type, CloseSpider):
            close(exc.reason)


session_config_registry = SessionConfigRulesRegistry()
session_config = session_config_registry.session_config


class _SessionManager:

    def __init__(self, crawler: Crawler):
        self._crawler = crawler

        settings = crawler.settings

        pool_size = settings.getint("ZYTE_API_SESSION_POOL_SIZE", 8)
        self._pending_initial_sessions: Dict[str, int] = defaultdict(lambda: pool_size)
        pool_sizes = settings.getdict("ZYTE_API_SESSION_POOL_SIZES", {})
        for pool, size in pool_sizes.items():
            self._pending_initial_sessions[pool] = size

        self._max_errors = settings.getint("ZYTE_API_SESSION_MAX_ERRORS", 1)
        self._errors: Dict[str, int] = defaultdict(int)

        max_bad_inits = settings.getint("ZYTE_API_SESSION_MAX_BAD_INITS", 8)
        self._max_bad_inits: Dict[str, int] = defaultdict(lambda: max_bad_inits)
        max_bad_inits_per_pool = settings.getdict(
            "ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL", {}
        )
        for pool, pool_max_bad_inits in max_bad_inits_per_pool.items():
            self._max_bad_inits[pool] = pool_max_bad_inits
        self._bad_inits: Dict[str, int] = defaultdict(int)

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
        self._pool_cache: WeakKeyDictionary[Request, str] = WeakKeyDictionary()

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
        self._queue_max_attempts = settings.getint(
            "ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS", 60
        )
        self._queue_wait_time = settings.getfloat(
            "ZYTE_API_SESSION_QUEUE_WAIT_TIME", 1.0
        )

        # Contains the on-going tasks to create new sessions.
        #
        # Keeping a reference to those tasks until they are done is necessary
        # to prevent garbage collection to remove the tasks.
        self._init_tasks: Set[Task] = set()

        self._session_config_cache: WeakKeyDictionary[Request, SessionConfig] = (
            WeakKeyDictionary()
        )
        self._session_config_map: Dict[Type[SessionConfig], SessionConfig] = {}

        self._setting_params = settings.getdict("ZYTE_API_SESSION_PARAMS")

        self._fatal_error_handler = FatalErrorHandler(crawler)

    def _get_session_config(self, request: Request) -> SessionConfig:
        try:
            return self._session_config_cache[request]
        except KeyError:
            cls = session_config_registry.session_config_cls(request)
            if cls not in self._session_config_map:
                self._session_config_map[cls] = _build_from_crawler(cls, self._crawler)
            self._session_config_cache[request] = self._session_config_map[cls]
            return self._session_config_map[cls]

    def _get_pool(self, request):
        try:
            return self._pool_cache[request]
        except KeyError:
            session_config = self._get_session_config(request)
            try:
                pool = session_config.pool(request)
            except Exception:
                raise PoolError
            self._pool_cache[request] = pool
            return pool

    async def _init_session(self, session_id: str, request: Request, pool: str) -> bool:
        assert self._crawler.engine
        assert self._crawler.stats
        session_config = self._get_session_config(request)
        if meta_params := request.meta.get("zyte_api_session_params", None):
            session_params = meta_params
        elif (
            not request.meta.get("zyte_api_session_location", None)
            and self._setting_params
        ):
            session_params = self._setting_params
        else:
            try:
                session_params = session_config.params(request)
            except Exception:
                self._crawler.stats.inc_value(
                    f"scrapy-zyte-api/sessions/pools/{pool}/init/param-error"
                )
                logger.exception(
                    f"Unexpected exception raised while obtaining session "
                    f"initialization parameters for request {request}."
                )
                return False
        session_params = deepcopy(session_params)
        session_init_url = session_params.pop("url", request.url)
        spider = self._crawler.spider
        session_init_request = Request(
            session_init_url,
            meta={
                SESSION_INIT_META_KEY: True,
                "dont_merge_cookies": True,
                "zyte_api": {**session_params, "session": {"id": session_id}},
                **{
                    k: v
                    for k, v in request.meta.items()
                    if k in {"zyte_api_session_location", "zyte_api_session_params"}
                },
            },
            callback=NO_CALLBACK,
        )
        if _DOWNLOAD_NEEDS_SPIDER:
            deferred = self._crawler.engine.download(  # type: ignore[call-arg]
                session_init_request, spider=spider
            )
        else:
            deferred = self._crawler.engine.download(session_init_request)
        try:
            response = await deferred_to_future(deferred)
        except Exception:
            self._crawler.stats.inc_value(
                f"scrapy-zyte-api/sessions/pools/{pool}/init/failed"
            )
            return False
        else:
            try:
                result = session_config.check(response, session_init_request)
            except CloseSpider:
                raise
            except Exception:
                self._crawler.stats.inc_value(
                    f"scrapy-zyte-api/sessions/pools/{pool}/init/check-error"
                )
                logger.exception(
                    f"Unexpected exception raised while checking session "
                    f"validity on response {response}."
                )
                return False
            outcome = "passed" if result else "failed"
            self._crawler.stats.inc_value(
                f"scrapy-zyte-api/sessions/pools/{pool}/init/check-{outcome}"
            )
        return result

    async def _create_session(self, request: Request, pool: str) -> str:
        with self._fatal_error_handler:
            while True:
                session_id = str(uuid4())
                session_init_succeeded = await self._init_session(
                    session_id, request, pool
                )
                if session_init_succeeded:
                    self._pools[pool].add(session_id)
                    self._bad_inits[pool] = 0
                    break
                self._bad_inits[pool] += 1
                if self._bad_inits[pool] >= self._max_bad_inits[pool]:
                    raise TooManyBadSessionInits
            self._queues[pool].append(session_id)
            return session_id

    async def _next_from_queue(self, request: Request, pool: str) -> str:
        session_id = None
        attempts = 0
        while session_id not in self._pools[pool]:  # After 1st loop: invalid session.
            try:
                session_id = self._queues[pool].popleft()
            except IndexError:  # No ready-to-use session available.
                attempts += 1
                if attempts >= self._queue_max_attempts:
                    raise RuntimeError(
                        f"Could not get a session ID from the session "
                        f"rotation queue after {attempts} attempts, waiting "
                        f"at least {self._queue_wait_time} seconds between "
                        f"attempts. Either the values of the "
                        f"ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS and "
                        f"ZYTE_API_SESSION_QUEUE_WAIT_TIME settings are too "
                        f"low for your scenario, in which case you can modify "
                        f"them accordingly, or there might be a bug with "
                        f"scrapy-zyte-api session management. If you think it "
                        f"could be the later, please report the issue at "
                        f"https://github.com/scrapy-plugins/scrapy-zyte-api/issues/new "
                        f"providing a minimal reproducible example if "
                        f"possible, or debug logs and stats otherwise."
                    )
                await sleep(self._queue_wait_time)
        assert session_id is not None
        self._queues[pool].append(session_id)
        return session_id

    async def _next(self, request) -> str:
        """Return the ID of the next working session in the session pool
        rotation.

        *request* is needed to determine the URL to use for request
        initialization.
        """
        pool = self._get_pool(request)
        if self._pending_initial_sessions[pool] >= 1:
            self._pending_initial_sessions[pool] -= 1
            session_id = await self._create_session(request, pool)
        else:
            session_id = await self._next_from_queue(request, pool)
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
        logger.warning(
            f"Request {request} had no session ID assigned, unexpectedly. "
            f"If you are sure this issue is not caused by your own code, "
            f"please report this at "
            f"https://github.com/scrapy-plugins/scrapy-zyte-api/issues/new "
            f"providing a minimal, reproducible example."
        )
        return None

    def _start_session_refresh(self, session_id: str, request: Request, pool: str):
        try:
            self._pools[pool].remove(session_id)
        except KeyError:
            # More than 1 request was using the same session concurrently. Do
            # not refresh the session again.
            pass
        else:
            task = create_task(self._create_session(request, pool))
            self._init_tasks.add(task)
            task.add_done_callback(self._init_tasks.discard)
        try:
            del self._errors[session_id]
        except KeyError:
            pass

    def _start_request_session_refresh(self, request: Request, pool: str):
        session_id = self._get_request_session_id(request)
        if session_id is None:
            return
        self._start_session_refresh(session_id, request, pool)

    async def check(self, response: Response, request: Request) -> bool:
        """Check the response for signs of session expiration, update the
        internal session pool accordingly, and return ``False`` if the session
        has expired or ``True`` if the session passed validation."""
        assert self._crawler.stats
        with self._fatal_error_handler:
            if self.is_init_request(request):
                return True
            session_config = self._get_session_config(request)
            if not session_config.enabled(request):
                return True
            pool = self._get_pool(request)
            try:
                passed = session_config.check(response, request)
            except CloseSpider:
                raise
            except Exception:
                self._crawler.stats.inc_value(
                    f"scrapy-zyte-api/sessions/pools/{pool}/use/check-error"
                )
                logger.exception(
                    f"Unexpected exception raised while checking session "
                    f"validity on response {response}."
                )
            else:
                outcome = "passed" if passed else "failed"
                self._crawler.stats.inc_value(
                    f"scrapy-zyte-api/sessions/pools/{pool}/use/check-{outcome}"
                )
                if passed:
                    return True
            self._start_request_session_refresh(request, pool)
        return False

    async def assign(self, request: Request):
        """Assign a working session to *request*."""
        assert self._crawler.stats
        with self._fatal_error_handler:
            if self.is_init_request(request):
                return
            session_config = self._get_session_config(request)
            if not session_config.enabled(request):
                self._crawler.stats.inc_value("scrapy-zyte-api/sessions/use/disabled")
                return
            session_id = await self._next(request)
            # Note: If there is a session set already (e.g. a request being
            # retried), it is overridden.
            request.meta.setdefault("zyte_api_provider", {})["session"] = {
                "id": session_id
            }
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
            request.meta.setdefault(meta_key, {})
            if not isinstance(request.meta[meta_key], dict):
                request.meta[meta_key] = {}
            request.meta[meta_key]["session"] = {"id": session_id}
            request.meta.setdefault("dont_merge_cookies", True)

    def is_enabled(self, request: Request) -> bool:
        session_config = self._get_session_config(request)
        return session_config.enabled(request)

    def handle_error(self, request: Request):
        assert self._crawler.stats
        with self._fatal_error_handler:
            pool = self._get_pool(request)
            self._crawler.stats.inc_value(
                f"scrapy-zyte-api/sessions/pools/{pool}/use/failed"
            )
            session_id = self._get_request_session_id(request)
            if session_id is not None:
                self._errors[session_id] += 1
                if self._errors[session_id] < self._max_errors:
                    return
            self._start_request_session_refresh(request, pool)

    def handle_expiration(self, request: Request):
        assert self._crawler.stats
        with self._fatal_error_handler:
            pool = self._get_pool(request)
            self._crawler.stats.inc_value(
                f"scrapy-zyte-api/sessions/pools/{pool}/use/expired"
            )
            self._start_request_session_refresh(request, pool)


class ScrapyZyteAPISessionDownloaderMiddleware:

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        return cls(crawler)

    def __init__(self, crawler: Crawler):
        self._crawler = crawler
        self._sessions = _SessionManager(crawler)

    async def process_request(self, request: Request, spider: Spider) -> None:
        await self._sessions.assign(request)

    async def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response, None]:
        if isinstance(response, DummyResponse):
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

    async def process_exception(
        self, request: Request, exception: Exception, spider: Spider
    ) -> Union[Request, None]:
        if (
            not isinstance(exception, RequestError)
            or self._sessions.is_init_request(request)
            or not self._sessions.is_enabled(request)
        ):
            return None

        if exception.parsed.type == "/problem/session-expired":
            self._sessions.handle_expiration(request)
            reason = "session_expired"
        elif exception.status in {520, 521}:
            self._sessions.handle_error(request)
            reason = "download_error"
        else:
            return None

        return get_retry_request(
            request,
            spider=spider,
            reason=reason,
        )


class LocationSessionConfig(SessionConfig):
    """:class:`~scrapy_zyte_api.SessionConfig` subclass to minimize boilerplate
    when implementing location-specific session configs, i.e. session configs
    where the default values should be used unless a location is set.

    Provides counterparts to some :class:`~scrapy_zyte_api.SessionConfig`
    methods that are only called when a location is set, and get that location
    as a parameter.
    """

    def params(self, request: Request) -> Dict[str, Any]:
        if not (location := self.location(request)):
            return super().params(request)
        return self.location_params(request, location)

    def check(self, response: Response, request: Request) -> bool:
        if not (location := self.location(request)):
            return super().check(response, request)
        return self.location_check(response, request, location)

    def location_params(
        self, request: Request, location: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Like :class:`SessionConfig.params
        <scrapy_zyte_api.SessionConfig.params>`, but it is only called when a
        location is set, and gets that *location* as a parameter."""
        return super().params(request)

    def location_check(
        self, response: Response, request: Request, location: Dict[str, Any]
    ) -> bool:
        """Like :class:`SessionConfig.check
        <scrapy_zyte_api.SessionConfig.check>`, but it is only called when a
        location is set, and gets that *location* as a parameter."""
        return super().check(response, request)
