from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, NamedTuple
from weakref import WeakKeyDictionary

from ._params import _BROWSER_KEYS

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler

    from ._params import _ParamParser


class _ProviderPlanData(NamedTuple):
    is_provider_only: bool
    to_provide: frozenset[object] | None
    http_response_available: bool


_HTTP_RESPONSE_KEYS = ("httpResponseBody", "httpResponseHeaders")

_plan_data_cache: WeakKeyDictionary[Request, _ProviderPlanData] = WeakKeyDictionary()
_injectors: WeakKeyDictionary[Crawler, Any] = WeakKeyDictionary()
_api_responses: WeakKeyDictionary[Request, dict[str, Any]] = WeakKeyDictionary()


def _analyze_provider_plan(injector, request: Request, plan) -> _ProviderPlanData:
    from scrapy_poet.injection import (  # noqa: PLC0415
        get_callback,
        is_callback_requiring_scrapy_response,
    )
    from web_poet import HttpResponse  # noqa: PLC0415

    from .providers import ZyteApiProvider  # noqa: PLC0415

    callback = get_callback(request, injector.spider)
    scrapy_response_required = is_callback_requiring_scrapy_response(
        callback,
        request.callback,
    )

    remaining_dependencies = {dependency for dependency, _kwargs in plan.dependencies}
    provided_dependencies: set = set()
    zyte_api_provider_dependencies: frozenset[object] | None = None
    http_response_available = False

    for provider in injector.providers:
        to_provide = {
            dependency
            for dependency in remaining_dependencies
            if provider.is_provided(dependency)
        }
        if not to_provide:
            continue

        if injector.is_provider_requiring_scrapy_response[provider]:
            scrapy_response_required = True

        if isinstance(provider, ZyteApiProvider):
            zyte_api_provider_dependencies = frozenset(to_provide)
            from andi.typeutils import strip_annotated  # noqa: PLC0415

            http_response_available = any(
                strip_annotated(dep) is HttpResponse for dep in provided_dependencies
            )

        provided_dependencies |= to_provide
        remaining_dependencies -= to_provide
        if not remaining_dependencies:
            break

    return _ProviderPlanData(
        is_provider_only=not scrapy_response_required,
        to_provide=zyte_api_provider_dependencies,
        http_response_available=(
            http_response_available
            if zyte_api_provider_dependencies is not None
            else False
        ),
    )


def _get_provider_plan_data(injector, request: Request) -> _ProviderPlanData:
    try:
        return _plan_data_cache[request]
    except KeyError:
        pass

    plan_data = _analyze_provider_plan(injector, request, injector.build_plan(request))
    _plan_data_cache[request] = plan_data
    return plan_data


def _get_injector(crawler: Crawler):
    """Return the scrapy-poet injector of *crawler*, or ``None`` if scrapy-poet
    is not in use."""
    try:
        return _injectors[crawler]
    except KeyError:
        pass

    try:
        from scrapy_poet import InjectionMiddleware  # noqa: PLC0415
    except ImportError:
        injector = None
    else:
        try:
            middleware = crawler.get_downloader_middleware(InjectionMiddleware)
        except AttributeError:  # Scrapy < 2.12
            middleware = None
            assert crawler.engine
            for component in crawler.engine.downloader.middleware.middlewares:
                if isinstance(component, InjectionMiddleware):
                    middleware = component
                    break
        injector = middleware.injector if middleware is not None else None

    _injectors[crawler] = injector
    return injector


def _merged_provider_request(
    request: Request, crawler: Crawler, param_parser: _ParamParser
) -> Request:
    """Return *request* with the Zyte API parameters that its scrapy-poet
    dependencies need folded into its own, or *request* unchanged when they
    cannot be combined into a single Zyte API request.
    """
    injector = _get_injector(crawler)
    if injector is None:
        return request

    plan_data = _get_provider_plan_data(injector, request)
    if plan_data.to_provide is None or plan_data.is_provider_only:
        return request

    explicit = param_parser.explicit_params(request)
    if explicit is None:
        return request
    meta_key, explicit_params = explicit

    from .providers import (  # noqa: PLC0415
        _get_or_build_zyte_api_provider_meta,
        _get_zyte_api_provider_params,
    )

    provider_params, _html_requested = _get_or_build_zyte_api_provider_meta(
        plan_data.to_provide,
        request,
        crawler,
        provider_params=_get_zyte_api_provider_params(request, crawler),
        http_response_available=plan_data.http_response_available,
    )

    for key, value in provider_params.items():
        if key in explicit_params and explicit_params[key] != value:
            return request

    # Browser outputs replace the HTTP response output, which Zyte API does not
    # allow in the same request. Keep 2 requests when the HTTP response is
    # explicitly requested or feeds a dependency of its own.
    if any(provider_params.get(key) for key in _BROWSER_KEYS) and (
        plan_data.http_response_available
        or any(explicit_params.get(key) for key in _HTTP_RESPONSE_KEYS)
    ):
        return request

    meta_params = request.meta.get(meta_key)
    if not isinstance(meta_params, Mapping):
        meta_params = {}
    return request.replace(
        meta={**request.meta, meta_key: {**meta_params, **provider_params}}
    )


def _set_api_response(request: Request, api_response: dict[str, Any]) -> None:
    _api_responses[request] = api_response


def _get_api_response(request: Request) -> dict[str, Any] | None:
    return _api_responses.get(request)
