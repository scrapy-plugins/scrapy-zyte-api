from functools import cached_property
from logging import getLogger
from typing import TYPE_CHECKING, cast

from ._session import ScrapyZyteAPISessionDownloaderMiddleware

logger = getLogger(__name__)

try:
    from scrapy.utils.request import (
        RequestFingerprinter as _RequestFingerprinter,  # noqa: F401
    )
except ImportError:
    if not TYPE_CHECKING:
        ScrapyZyteAPIRequestFingerprinter = None
else:
    import hashlib
    import json
    from base64 import b64encode
    from weakref import WeakKeyDictionary

    from scrapy import Request
    from scrapy.settings.default_settings import (
        REQUEST_FINGERPRINTER_CLASS as ScrapyRequestFingerprinter,
    )
    from scrapy.utils.misc import load_object
    from w3lib.url import canonicalize_url

    from ._params import _REQUEST_PARAMS, _may_use_browser, _ParamParser
    from .utils import _build_from_crawler  # type: ignore[attr-defined]

    class ScrapyZyteAPIRequestFingerprinter:
        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        @staticmethod
        def _poet_is_configured(settings):
            try:
                from scrapy_poet import InjectionMiddleware  # noqa: PLC0415
            except ImportError:
                return False
            for k, v in settings.get("DOWNLOADER_MIDDLEWARES", {}).items():
                if issubclass(load_object(k), InjectionMiddleware):
                    return v is not None
            return False

        def __init__(self, crawler):
            settings = crawler.settings
            self._fallback_fingerprinter_is_poets = poet_is_configured = (
                self._poet_is_configured(settings)
            )
            DefaultFallbackRequestFingerprinter: type | str
            if poet_is_configured:
                from scrapy_poet import (  # noqa: PLC0415
                    ScrapyPoetRequestFingerprinter as DefaultFallbackRequestFingerprinter,
                )
            else:
                DefaultFallbackRequestFingerprinter = ScrapyRequestFingerprinter
            self._fallback_request_fingerprinter = _build_from_crawler(
                load_object(
                    settings.get(
                        "ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS",
                        DefaultFallbackRequestFingerprinter,
                    )
                ),
                crawler,
            )
            if poet_is_configured and not isinstance(
                self._fallback_request_fingerprinter,
                cast("type", DefaultFallbackRequestFingerprinter),
            ):
                logger.warning(
                    f"scrapy-poet is enabled, but your custom value for the "
                    f"ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS setting "
                    f"({settings['ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS']!r})"
                    f" does not point to a subclass of "
                    f"scrapy_poet.ScrapyPoetRequestFingerprinter. For request "
                    f"fingerprinting to work properly, consider switching "
                    f"ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS to "
                    f"scrapy_poet.ScrapyPoetRequestFingerprinter or a "
                    f"subclass. You can move your current value of the "
                    f"ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS setting "
                    f"to the SCRAPY_POET_REQUEST_FINGERPRINTER_BASE_CLASS "
                    f"setting instead."
                )
                self._fallback_fingerprinter_is_poets = False
            self._cache: WeakKeyDictionary[Request, bytes] = WeakKeyDictionary()
            self._provider_only_cache: WeakKeyDictionary[Request, bool] = (
                WeakKeyDictionary()
            )
            self._param_parser = _ParamParser(crawler, cookies_enabled=False)
            self._crawler = crawler

        def _normalize_params(self, api_params):
            api_params["url"] = canonicalize_url(
                api_params["url"],
                keep_fragments=_may_use_browser(api_params),
            )

            if "httpRequestText" in api_params:
                api_params["httpRequestBody"] = b64encode(
                    api_params.pop("httpRequestText").encode()
                ).decode()

            for key, value in _REQUEST_PARAMS.items():
                if not value.get("changes_fingerprint", True):
                    api_params.pop(key, None)

        @cached_property
        def _session_mw(self):
            try:
                mw = self._crawler.get_downloader_middleware(
                    ScrapyZyteAPISessionDownloaderMiddleware
                )
            except AttributeError:  # Scrapy < 2.12
                for component in self._crawler.engine.downloader.middleware.middlewares:
                    if isinstance(component, ScrapyZyteAPISessionDownloaderMiddleware):
                        mw = component
                        break
                else:
                    mw = None
            if mw is None:

                class NoOpSessionDownloaderMiddleware:
                    def get_pool(self, request):
                        return None

                mw = NoOpSessionDownloaderMiddleware()
            return mw

        def _get_pool(self, request: Request) -> str | None:
            return self._session_mw.get_pool(request)

        def _serialize_api_params(self, request: Request, api_params) -> bytes:
            session_pool = self._get_pool(request)
            if session_pool is not None:
                api_params.setdefault("sessionContext", session_pool)
            self._normalize_params(api_params)
            return json.dumps(api_params, sort_keys=True).encode()

        @staticmethod
        def _hash_fingerprint(fingerprint_data: bytes) -> bytes:
            return hashlib.sha1(fingerprint_data, usedforsecurity=False).digest()

        @staticmethod
        def _contains_dependency(dependencies, dependency_cls) -> bool:
            from andi.typeutils import strip_annotated  # noqa: PLC0415

            return any(
                strip_annotated(dependency) is dependency_cls
                for dependency in dependencies
            )

        @staticmethod
        def _is_scrapy_response_required(injector, request: Request, plan) -> bool:
            from scrapy_poet.injection import (  # noqa: PLC0415
                get_callback,
                is_callback_requiring_scrapy_response,
            )

            callback = get_callback(request, injector.spider)
            if is_callback_requiring_scrapy_response(callback, request.callback):
                return True

            for dependency, _ in plan.dependencies:
                for provider in injector.providers:
                    if not injector.is_provider_requiring_scrapy_response[provider]:
                        continue
                    if provider.is_provided(dependency):
                        return True

            return False

        def _is_provider_only_request(self, request: Request) -> bool:
            if not self._fallback_fingerprinter_is_poets:
                return False

            try:
                return self._provider_only_cache[request]
            except KeyError:
                pass

            injector = self._fallback_request_fingerprinter._injector
            plan = injector.build_plan(request)
            return self._set_provider_only_cache(
                request,
                injector,
                plan,
            )

        def _set_provider_only_cache(self, request: Request, injector, plan) -> bool:
            is_provider_only = not self._is_scrapy_response_required(
                injector,
                request,
                plan,
            )
            self._provider_only_cache[request] = is_provider_only
            return is_provider_only

        def _get_regular_request_fingerprint(self, request: Request) -> bytes | None:
            api_params = self._param_parser.parse(request)
            if api_params is None:
                return None

            fingerprint = self._serialize_api_params(request, api_params)
            if self._fallback_fingerprinter_is_poets:
                deps_key = self._fallback_request_fingerprinter.get_deps_key(request)
                serialized_page_params = (
                    self._fallback_request_fingerprinter.serialize_page_params(request)
                )
                for extra_fingerprint_part in (deps_key, serialized_page_params):
                    if extra_fingerprint_part is not None:
                        fingerprint += extra_fingerprint_part
            return self._hash_fingerprint(fingerprint)

        def _get_provider_request_fingerprint(self, request: Request) -> bytes | None:
            if not self._fallback_fingerprinter_is_poets:
                return None

            from web_poet import HttpResponse  # noqa: PLC0415

            from .providers import (  # noqa: PLC0415
                ZyteApiProvider,
                _build_zyte_api_provider_meta,
            )

            injector = self._fallback_request_fingerprinter._injector
            plan = injector.build_plan(request)

            dependencies = {dependency for dependency, _ in plan.dependencies}
            self._set_provider_only_cache(
                request,
                injector,
                plan,
            )

            remaining_dependencies = set(dependencies)
            provided_dependencies: set = set()

            for provider in injector.providers:
                to_provide = {
                    dependency
                    for dependency in remaining_dependencies
                    if provider.is_provided(dependency)
                }
                if not to_provide:
                    continue
                if isinstance(provider, ZyteApiProvider):
                    api_params, _html_requested = _build_zyte_api_provider_meta(
                        to_provide,
                        request,
                        self._crawler,
                        http_response_available=self._contains_dependency(
                            provided_dependencies,
                            HttpResponse,
                        ),
                    )
                    api_params["url"] = request.url
                    return self._hash_fingerprint(
                        self._serialize_api_params(request, api_params)
                    )
                provided_dependencies |= to_provide
                remaining_dependencies -= to_provide

            return None

        def fingerprint(self, request):
            if request in self._cache:
                return self._cache[request]

            provider_fingerprint = self._get_provider_request_fingerprint(request)
            if provider_fingerprint is not None and self._is_provider_only_request(
                request
            ):
                self._cache[request] = provider_fingerprint
                return self._cache[request]

            regular_fingerprint = self._get_regular_request_fingerprint(request)

            if regular_fingerprint is not None and provider_fingerprint is not None:
                self._cache[request] = self._hash_fingerprint(
                    regular_fingerprint + provider_fingerprint
                )
                return self._cache[request]

            if regular_fingerprint is not None:
                self._cache[request] = regular_fingerprint
                return self._cache[request]

            if provider_fingerprint is not None:
                self._cache[request] = provider_fingerprint
                return self._cache[request]

            return self._fallback_request_fingerprinter.fingerprint(request)
