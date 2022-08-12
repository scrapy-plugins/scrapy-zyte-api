import logging
from base64 import b64decode, b64encode
from typing import Any, Dict, Generator, Optional, Union
from warnings import warn

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.settings.default_settings import (
    DEFAULT_REQUEST_HEADERS,
    USER_AGENT as DEFAULT_USER_AGENT
)
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session
from zyte_api.aio.errors import RequestError
from zyte_api.apikey import NoApiKey
from zyte_api.constants import API_URL

from .responses import ZyteAPIResponse, ZyteAPITextResponse, _process_response

logger = logging.getLogger(__name__)


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncClient = None
    ):
        super().__init__(settings=settings, crawler=crawler)
        if not settings.getbool("ZYTE_API_ENABLED", True):
            raise NotConfigured
        if not client:
            try:
                client = AsyncClient(
                    # To allow users to have a key defined in Scrapy settings
                    # and in a environment variable, and be able to cause the
                    # environment variable to be used instead of the setting by
                    # overriding the setting on the command-line to be an empty
                    # string, we do not support setting empty string keys
                    # through settings.
                    api_key=settings.get("ZYTE_API_KEY") or None,
                    api_url=settings.get("ZYTE_API_URL") or API_URL,
                    n_conn=settings.getint("CONCURRENT_REQUESTS"),
                )
            except NoApiKey:
                logger.warning(
                    "'ZYTE_API_KEY' must be set in the spider settings or env var "
                    "in order for ScrapyZyteAPIDownloadHandler to work."
                )
                raise NotConfigured
        self._client: AsyncClient = client
        logger.info(
            "Using a Zyte Data API key starting with %r", self._client.api_key[:7]
        )
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        self._stats = crawler.stats
        self._job_id = crawler.settings.get("JOB")
        self._zyte_api_default_params = settings.getdict("ZYTE_API_DEFAULT_PARAMS")
        self._session = create_session(connection_pool_size=self._client.n_conn)
        self._retry_policy = settings.get("ZYTE_API_RETRY_POLICY")
        self._on_all_requests = settings.getbool("ZYTE_API_ON_ALL_REQUESTS")
        self._automap = settings.getbool("ZYTE_API_AUTOMAP", True)
        self._unsupported_headers = {
            header.strip().lower().encode() for header in settings.getlist(
                "ZYTE_API_UNSUPPORTED_HEADERS",
                ["Cookie", "User-Agent"],
            )
        }
        browser_headers = settings.getdict(
            "ZYTE_API_BROWSER_HEADERS",
            {"Referer": "referer"},
        )
        self._browser_headers = {
            k.strip().lower().encode(): v
            for k, v in browser_headers.items()
        }

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        api_params = self._prepare_api_params(request)
        if api_params:
            return deferred_from_coro(
                self._download_request(api_params, request, spider)
            )
        return super().download_request(request, spider)

    def _prepare_api_params(self, request: Request) -> Optional[dict]:
        meta_params = request.meta.get("zyte_api", self._on_all_requests)
        if meta_params is False:
            return None
        if not meta_params and meta_params != {}:
            warn(
                f"Setting the zyte_api request metadata key to "
                f"{meta_params!r} is deprecated. Use False instead.",
                DeprecationWarning,
            )
            return None
        if meta_params is True:
            meta_params = {}

        api_params: Dict[str, Any] = self._zyte_api_default_params or {}
        try:
            api_params.update(meta_params)
        except TypeError:
            logger.error(
                f"zyte_api parameters in the request meta should be "
                f"provided as dictionary, got {type(request.meta.get('zyte_api'))} "
                f"instead ({request.url})."
            )
            raise IgnoreRequest()

        if not self._automap:
            return api_params

        if not any(
            api_params.get(k)
            for k in ("httpResponseBody", "browserHtml", "screenshot")
        ):
            api_params.setdefault("httpResponseBody", True)
        response_body = api_params.get("httpResponseBody")

        if any(api_params.get(k) for k in ("httpResponseBody", "browserHtml")):
            if api_params.get("httpResponseHeaders") is True:
                logger.warning(
                    "You do not need to set httpResponseHeaders to True if "
                    "you httpResponseBody or browserHtml to True. Note that "
                    "httpResponseBody is set to True automatically if neither "
                    "browserHtml nor screenshot are set to True."
                )
            api_params.setdefault("httpResponseHeaders", True)

        method = api_params.get("httpRequestMethod")
        if method:
            logger.warning(
                f"Request {request} uses the Zyte Data API httpRequestMethod "
                f"parameter. Use Request.method instead."
            )
            if method != request.method:
                logger.warning(
                    f"The HTTP method of request {request} ({request.method}) "
                    f"does not match the Zyte Data API httpRequestMethod "
                    f"parameter ({method})."
                )
        elif request.method != "GET":
            if response_body:
                api_params["httpRequestMethod"] = request.method
            else:
                logger.warning(
                    f"The HTTP method of request {request} ({request.method}) "
                    f"is being ignored. The httpRequestMethod parameter of "
                    f"Zyte Data API can only be set when the httpResponseBody "
                    f"parameter is True."
                )

        if response_body:
            headers = api_params.get("customHttpRequestHeaders")
            if headers is not None:
                logger.warning(
                    f"Request {request} defines the Zyte Data API "
                    f"customHttpRequestHeaders parameter. Use Request.headers "
                    f"instead."
                )
            elif request.headers:
                headers = []
                for k, v in request.headers.items():
                    if not v:
                        continue
                    v = b','.join(v).decode()
                    lowercase_k = k.strip().lower()
                    if lowercase_k in self._unsupported_headers:
                        if (
                            lowercase_k != b'user-agent'
                            or v != DEFAULT_USER_AGENT
                        ):
                            logger.warning(
                                f"Request {request} defines header {k}, which "
                                f"cannot be mapped into the Zyte Data API "
                                f"customHttpRequestHeaders parameter."
                            )
                        continue
                    k = k.decode()
                    headers.append({"name": k, "value": v})
                if headers:
                    api_params["customHttpRequestHeaders"] = headers
        if (
            not response_body
            or any(api_params.get(k) for k in ("browserHtml", "screenshot"))
        ):
            headers = api_params.get("requestHeaders")
            if headers is not None:
                logger.warning(
                    f"Request {request} defines the Zyte Data API "
                    f"requestHeaders parameter. Use Request.headers instead."
                )
            elif request.headers:
                request_headers = {}
                for k, v in request.headers.items():
                    if not v:
                        continue
                    v = b','.join(v).decode()
                    lowercase_k = k.strip().lower()
                    key = self._browser_headers.get(lowercase_k)
                    if key is not None:
                        request_headers[key] = v
                    elif not (
                        (
                            lowercase_k == b'accept'
                            and v == DEFAULT_REQUEST_HEADERS['Accept']
                        ) or (
                            lowercase_k == b'accept-language'
                            and v == DEFAULT_REQUEST_HEADERS['Accept-Language']
                        ) or (
                            lowercase_k == b'user-agent'
                            and v == DEFAULT_USER_AGENT
                        )
                    ):
                        logger.warning(
                            f"Request {request} defines header {k}, which "
                            f"cannot be mapped into the Zyte Data API "
                            f"requestHeaders parameter."
                        )
                if request_headers:
                    api_params["requestHeaders"] = request_headers

        body = api_params.get("httpRequestBody")
        if body:
            logger.warning(
                f"Request {request} uses the Zyte Data API httpRequestBody "
                f"parameter. Use Request.body instead."
            )
            decoded_body = b64decode(body)
            if decoded_body != request.body:
                logger.warning(
                    f"The body of request {request} ({request.body!r}) "
                    f"does not match the Zyte Data API httpRequestBody "
                    f"parameter ({body!r}; decoded: {decoded_body!r})."
                )
        elif request.body != b"":
            if response_body:
                base64_body = b64encode(request.body).decode()
                api_params["httpRequestBody"] = base64_body
            else:
                logger.warning(
                    f"The body of request {request} ({request.body!r}) "
                    f"is being ignored. The httpRequestBody parameter of "
                    f"Zyte Data API can only be set when the httpResponseBody "
                    f"parameter is True."
                )

        return api_params

    def _update_stats(self):
        prefix = "scrapy-zyte-api"
        for stat in (
            '429',
            'attempts',
            'errors',
            'fatal_errors',
            'processed',
            'success',
        ):
            self._stats.set_value(
                f"{prefix}/{stat}",
                getattr(self._client.agg_stats, f"n_{stat}"),
            )
        for stat in (
            'error_ratio',
            'success_ratio',
            'throttle_ratio',
        ):
            self._stats.set_value(
                f"{prefix}/{stat}",
                getattr(self._client.agg_stats, stat)(),
            )
        for source, target in (
            ('connect', 'connection'),
            ('total', 'response'),
        ):
            self._stats.set_value(
                f"{prefix}/mean_{target}_seconds",
                getattr(self._client.agg_stats, f"time_{source}_stats").mean(),
            )

        for error_type, count in self._client.agg_stats.api_error_types.items():
            error_type = error_type or "/<empty>"
            if not error_type.startswith("/"):
                error_type = f"/{error_type}"
            self._stats.set_value(f"{prefix}/error_types{error_type}", count)

        for counter in ('exception_types', 'status_codes',):
            for key, value in getattr(self._client.agg_stats, counter).items():
                self._stats.set_value(f"{prefix}/{counter}/{key}", value)

    async def _download_request(
        self, api_params: dict, request: Request, spider: Spider
    ) -> Optional[Union[ZyteAPITextResponse, ZyteAPIResponse]]:
        # Define url by default
        api_data = {**{"url": request.url}, **api_params}
        if self._job_id is not None:
            api_data["jobId"] = self._job_id
        retrying = request.meta.get("zyte_api_retry_policy") or self._retry_policy
        try:
            api_response = await self._client.request_raw(
                api_data,
                session=self._session,
                retrying=retrying,
            )
        except RequestError as er:
            error_detail = (er.parsed.data or {}).get("detail", er.message)
            logger.error(
                f"Got Zyte API error (status={er.status}, type={er.parsed.type!r}) "
                f"while processing URL ({request.url}): {error_detail}"
            )
            raise IgnoreRequest()
        except Exception as er:
            logger.error(
                f"Got an error when processing Zyte API request ({request.url}): {er}"
            )
            raise IgnoreRequest()
        finally:
            self._update_stats()

        return _process_response(api_response, request)

    @inlineCallbacks
    def close(self) -> Generator:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()
