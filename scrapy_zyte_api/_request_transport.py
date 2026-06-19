from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._proxy import _get_unknown_proxy_mode_headers, _is_proxy_mode_compatible
from ._request_type import is_manual_request

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.settings import Settings

_VALID_TRANSPORTS = ("auto", "http", "proxy")


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


def _resolve_auto_transport(
    request: Request, api_params: dict[str, Any], auth_type: str
) -> str:
    if auth_type != "zyte":
        return "http"
    if _is_proxy_mode_compatible(api_params):
        return "proxy"
    # The parameters are not proxy-compatible. Only proxy mode could honor any
    # Zyte-* headers on the request, but it cannot run these parameters, so the
    # request falls back to the HTTP API — unless it carries an unknown Zyte-*
    # header, whose effect cannot be reproduced through the HTTP API. In that
    # case it stays in proxy mode so the handler reports a hard error instead of
    # silently dropping the header.
    if _get_unknown_proxy_mode_headers(request):
        return "proxy"
    return "http"


def _resolve_transport(
    request: Request, api_params: dict[str, Any], settings: Settings, auth_type: str
) -> tuple[str, str]:
    """Returns (assigned_transport, effective_transport).

    assigned_transport is "auto", "proxy", or "http".
    effective_transport is "proxy" or "http" — "auto" is resolved based on
    request data.
    """
    assigned_transport = _get_assigned_transport(request, settings)
    if assigned_transport != "auto":
        return assigned_transport, assigned_transport
    return "auto", _resolve_auto_transport(request, api_params, auth_type)
