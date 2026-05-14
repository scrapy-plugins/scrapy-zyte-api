import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from scrapy.crawler import Crawler

_ProviderMetaSharedCacheKey = tuple[
    frozenset[object],
    bool,
    str,
]
_ProviderMetaSharedCacheEntry = tuple[dict[str, object], bool]

_PROVIDER_META_SHARED_CACHE_MAX_SIZE = 1024

_K = TypeVar("_K")
_V = TypeVar("_V")


@dataclass
class _ProviderFingerprintCacheState:
    provider_meta_shared_cache_max_size: int = _PROVIDER_META_SHARED_CACHE_MAX_SIZE
    provider_meta_by_key_cache: OrderedDict[
        _ProviderMetaSharedCacheKey,
        _ProviderMetaSharedCacheEntry,
    ] = field(default_factory=OrderedDict)


_PROVIDER_FINGERPRINT_CACHE_STATES: WeakKeyDictionary[
    object,
    _ProviderFingerprintCacheState,
] = WeakKeyDictionary()


def _get_provider_fingerprint_cache_state(
    crawler: "Crawler",
) -> _ProviderFingerprintCacheState:
    try:
        return _PROVIDER_FINGERPRINT_CACHE_STATES[crawler]
    except KeyError:
        cache_state = _ProviderFingerprintCacheState()
        _PROVIDER_FINGERPRINT_CACHE_STATES[crawler] = cache_state
        return cache_state


def _cacheable_meta_value(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _set_cached_lru_data(
    cache: OrderedDict[_K, _V],
    cache_key: _K,
    cache_value: _V,
    *,
    max_size: int,
) -> None:
    if max_size <= 0:
        return

    cache[cache_key] = cache_value
    cache.move_to_end(cache_key)

    while len(cache) > max_size:
        cache.popitem(last=False)


def _get_cached_lru_data(
    cache: OrderedDict[_K, _V],
    cache_key: _K,
) -> _V | None:
    try:
        cache_value = cache[cache_key]
    except KeyError:
        return None

    cache.move_to_end(cache_key)
    return cache_value


def _get_provider_meta_cache_key(
    *,
    to_provide,
    http_response_available: bool,
    provider_params_key: str,
) -> _ProviderMetaSharedCacheKey:
    return (
        frozenset(to_provide),
        http_response_available,
        provider_params_key,
    )


def _get_zyte_api_provider_meta_cache_key(
    *,
    to_provide,
    http_response_available: bool,
    provider_params,
) -> _ProviderMetaSharedCacheKey:
    return _get_provider_meta_cache_key(
        to_provide=to_provide,
        http_response_available=http_response_available,
        provider_params_key=_cacheable_meta_value(provider_params),
    )


def _set_cached_shared_zyte_api_provider_meta(
    cache_state: _ProviderFingerprintCacheState,
    cache_key: _ProviderMetaSharedCacheKey,
    cache_value: _ProviderMetaSharedCacheEntry,
) -> None:
    _set_cached_lru_data(
        cache_state.provider_meta_by_key_cache,
        cache_key,
        cache_value,
        max_size=cache_state.provider_meta_shared_cache_max_size,
    )


def _get_cached_shared_zyte_api_provider_meta(
    cache_state: _ProviderFingerprintCacheState,
    cache_key: _ProviderMetaSharedCacheKey,
) -> _ProviderMetaSharedCacheEntry | None:
    return _get_cached_lru_data(
        cache_state.provider_meta_by_key_cache,
        cache_key,
    )


def _set_cached_zyte_api_provider_meta_by_cache_key(
    cache_state: _ProviderFingerprintCacheState,
    *,
    cache_key: _ProviderMetaSharedCacheKey,
    zyte_api_meta,
    html_requested: bool,
) -> None:
    _set_cached_shared_zyte_api_provider_meta(
        cache_state,
        cache_key,
        (
            dict(zyte_api_meta),
            html_requested,
        ),
    )


def _get_cached_zyte_api_provider_meta_by_cache_key(
    cache_state: _ProviderFingerprintCacheState,
    *,
    cache_key: _ProviderMetaSharedCacheKey,
) -> tuple[dict, bool] | None:
    shared_cache_value = _get_cached_shared_zyte_api_provider_meta(
        cache_state,
        cache_key,
    )
    if shared_cache_value is None:
        return None
    cached_zyte_api_meta, cached_html_requested = shared_cache_value

    return dict(cached_zyte_api_meta), cached_html_requested


def _set_cached_zyte_api_provider_meta(
    cache_state: _ProviderFingerprintCacheState,
    *,
    to_provide,
    http_response_available: bool,
    provider_params,
    zyte_api_meta,
    html_requested: bool,
) -> _ProviderMetaSharedCacheKey:
    shared_cache_key = _get_zyte_api_provider_meta_cache_key(
        to_provide=to_provide,
        http_response_available=http_response_available,
        provider_params=provider_params,
    )
    _set_cached_zyte_api_provider_meta_by_cache_key(
        cache_state,
        cache_key=shared_cache_key,
        zyte_api_meta=zyte_api_meta,
        html_requested=html_requested,
    )
    return shared_cache_key


def _get_cached_zyte_api_provider_meta(
    cache_state: _ProviderFingerprintCacheState,
    *,
    to_provide,
    http_response_available: bool,
    provider_params,
) -> tuple[dict, bool] | None:
    shared_cache_key = _get_zyte_api_provider_meta_cache_key(
        to_provide=to_provide,
        http_response_available=http_response_available,
        provider_params=provider_params,
    )
    return _get_cached_zyte_api_provider_meta_by_cache_key(
        cache_state,
        cache_key=shared_cache_key,
    )
