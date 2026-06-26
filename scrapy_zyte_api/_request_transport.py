from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from ._proxy import (
    _get_proxy_incompatible_params,
    _get_unknown_proxy_mode_headers,
    _has_proxy_mode_headers,
    _proxy_headers_exceed_limit,
    _proxy_uses_browser_rendering,
)
from ._request_type import is_manual_request

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.settings import Settings

_VALID_TRANSPORTS = ("auto", "http", "proxy")


class _TransportResolution(NamedTuple):
    assigned: str
    effective: str
    experimental: str | None
    incompatible: list[str]


def _validate_transport(transport: str, *, source: str) -> str:
    """Validate a request transport value, raising :exc:`ValueError` if it is
    not one of the supported transports."""
    if transport not in _VALID_TRANSPORTS:
        valid = ", ".join(repr(value) for value in _VALID_TRANSPORTS)
        raise ValueError(
            f"Invalid request transport {transport!r} (from {source}). Supported "
            f"request transports are: {valid}."
        )
    return transport


def _resolve_configured_transport(
    *,
    meta_value: str | None,
    setting_value: str | None,
    meta_source: str,
    setting_source: str,
) -> tuple[str, bool]:
    """Resolve a request transport configured through a request metadata key
    and a setting, returning ``(transport, explicit)``.

    The metadata value takes precedence over the setting value. *explicit* is
    ``True`` when either value is set (and thus validated), and ``False`` when
    both are unset and the transport defaults to ``"auto"``.

    This is shared by the configuration of the scrapy-poet provider transport
    (see :class:`~scrapy_zyte_api.providers.ZyteApiProvider`) and the session
    initialization transport (see
    :class:`scrapy_zyte_api._session._SessionManager`).
    """
    if meta_value is not None:
        return _validate_transport(meta_value, source=meta_source), True
    if setting_value is not None:
        return _validate_transport(setting_value, source=setting_source), True
    return "auto", False


def _get_assigned_transport(request: Request, settings: Settings) -> str:
    """Returns "auto", "http" or "proxy", whichever the request is supposed to
    use."""
    transport = request.meta.get("zyte_api_transport")
    if transport is not None:
        return _validate_transport(
            transport, source="the zyte_api_transport request.meta key"
        )
    if is_manual_request(request):
        return "http"
    return _validate_transport(
        settings.get("ZYTE_API_TRANSPORT", "auto"),
        source="the ZYTE_API_TRANSPORT setting",
    )


def _transport_is_explicit(request: Request, settings: Settings) -> bool:
    """Return whether the request transport was explicitly configured by the
    user (through a setting or a request metadata key) as opposed to being left
    at its default value.

    While proxy mode is :ref:`experimental <experimental-proxy>`, it is only
    used when the transport is explicitly configured; otherwise the request
    falls back to the HTTP API (see :func:`_resolve_transport`)."""
    # Set by the scrapy-poet provider to reflect whether the provider transport
    # was explicitly configured, since the generated request always carries a
    # zyte_api_transport metadata key and would otherwise look explicit.
    explicit = request.meta.get("_zyte_api_transport_explicit")
    if explicit is not None:
        return bool(explicit)
    if request.meta.get("zyte_api_transport") is not None:
        return True
    if is_manual_request(request):
        # Manual requests default to "http"; only the zyte_api_transport
        # metadata key (handled above) can opt them into proxy mode.
        return False
    if settings.get("ZYTE_API_TRANSPORT") is not None:
        return True
    # For requests routed through proxy mode because they carry Zyte-* headers,
    # enabling ZYTE_API_HEADER_TRANSPORT_ENABLED is also an explicit opt-in into
    # proxy mode. (Disabling it, or leaving it unset, is not: a disabled value
    # keeps such headers from triggering proxy mode at all, while an unset value
    # leaves the request subject to experimental gating.)
    return _has_proxy_mode_headers(request) and settings.getbool(
        "ZYTE_API_HEADER_TRANSPORT_ENABLED"
    )


def _resolve_auto_transport(
    request: Request,
    api_params: dict[str, Any],
    auth_type: str,
    *,
    incompatible: list[str] | None = None,
    unknown_headers: list[str] | None = None,
) -> str:
    """Resolve the effective transport of an ``"auto"`` request.

    *incompatible* and *unknown_headers* let a caller pass in values it has
    already computed (see :func:`_resolve_transport`) to avoid recomputing them;
    any left as ``None`` is computed on demand.
    """
    if auth_type != "zyte":
        return "http"
    if incompatible is None:
        browser_rendering = _proxy_uses_browser_rendering(request, api_params)
        incompatible = _get_proxy_incompatible_params(
            api_params, browser_rendering=browser_rendering
        )
    if unknown_headers is None:
        unknown_headers = _get_unknown_proxy_mode_headers(request)
    if not incompatible:
        if _proxy_headers_exceed_limit(request, api_params) and not unknown_headers:
            return "http"
        return "proxy"
    # The parameters are not proxy-compatible. Only proxy mode could honor any
    # Zyte-* headers on the request, but it cannot run these parameters, so the
    # request falls back to the HTTP API — unless it carries an unknown Zyte-*
    # header, whose effect cannot be reproduced through the HTTP API. In that
    # case it stays in proxy mode so the handler reports a hard error instead of
    # silently dropping the header. (Whether Zyte-* headers route the request
    # through Zyte API in the first place is decided earlier, when automap is
    # enabled; see ZYTE_API_HEADER_TRANSPORT_ENABLED.)
    if unknown_headers:
        return "proxy"
    return "http"


def _header_is_decisive(
    request: Request, settings: Settings, header_transport_enabled: bool
) -> bool:
    """Return whether *request* would be routed through proxy mode specifically
    because it carries ``Zyte-*`` headers — i.e. the headers make the
    difference, with no other setting or request metadata key opting the request
    into Zyte API on their own.

    This is only ever called for requests that already reached experimental
    gating, which guarantees an ``"auto"`` transport that is not explicitly
    configured (so :reqmeta:`zyte_api`, :reqmeta:`zyte_api_transport` and the
    :setting:`ZYTE_API_TRANSPORT` setting are all ruled out already). What
    remains to check is that the headers, rather than :ref:`transparent mode
    <transparent>` or an explicit :reqmeta:`zyte_api_automap`, are what put the
    request on the Zyte API automap track."""
    return (
        header_transport_enabled
        and _has_proxy_mode_headers(request)
        and "zyte_api_automap" not in request.meta
        and not settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
    )


def _resolve_transport(
    request: Request,
    api_params: dict[str, Any],
    settings: Settings,
    auth_type: str,
    header_transport_enabled: bool,
) -> _TransportResolution:
    """Resolve how *request* should be downloaded.

    ``assigned`` is "auto", "proxy", or "http".

    ``effective`` is "proxy" or "http" — "auto" is resolved based on request
    data.

    ``experimental`` indicates that the request would use proxy mode if the
    feature were enabled by default, but is being sent through the HTTP API
    instead because proxy mode is :ref:`experimental <experimental-proxy>` and
    the transport was not explicitly configured. It is ``None`` when no such
    fallback happens, ``"header"`` when the request is eligible specifically
    because it carries ``Zyte-*`` headers (see :func:`_header_is_decisive`),
    and ``"transport"`` otherwise.

    ``incompatible`` lists the proxy-incompatible parameters; it is computed
    here (once) so the handler can reuse it, and is only meaningful when
    ``effective`` is "proxy".
    """
    assigned_transport = _get_assigned_transport(request, settings)
    if assigned_transport == "http":
        return _TransportResolution("http", "http", None, [])
    browser_rendering = _proxy_uses_browser_rendering(request, api_params)
    incompatible = _get_proxy_incompatible_params(
        api_params, browser_rendering=browser_rendering
    )
    if assigned_transport == "proxy":
        return _TransportResolution("proxy", "proxy", None, incompatible)
    unknown_headers = _get_unknown_proxy_mode_headers(request)
    effective_transport = _resolve_auto_transport(
        request,
        api_params,
        auth_type,
        incompatible=incompatible,
        unknown_headers=unknown_headers,
    )
    if effective_transport == "proxy" and not _transport_is_explicit(request, settings):
        if _header_is_decisive(request, settings, header_transport_enabled):
            return _TransportResolution("auto", "http", "header", incompatible)
        return _TransportResolution("auto", "http", "transport", incompatible)
    return _TransportResolution("auto", effective_transport, None, incompatible)
