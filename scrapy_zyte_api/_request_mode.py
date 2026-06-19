from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._proxy import _get_unknown_proxy_mode_headers, _is_proxy_mode_compatible
from ._request_type import is_manual_request

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.settings import Settings

_VALID_MODES = ("auto", "http", "proxy")


def _validate_mode(mode: str, *, source: str) -> str:
    """Validate a request mode value, raising :exc:`ValueError` if it is not
    one of the supported modes."""
    if mode not in _VALID_MODES:
        valid = ", ".join(repr(value) for value in _VALID_MODES)
        raise ValueError(
            f"Invalid request mode {mode!r} (from {source}). Supported request "
            f"modes are: {valid}."
        )
    return mode


def _get_assigned_mode(request: Request, settings: Settings) -> str:
    """Returns "auto", "http" or "proxy", whichever the request is supposed to
    use."""
    mode = request.meta.get("zyte_api_mode")
    if mode is not None:
        return _validate_mode(mode, source="the zyte_api_mode request.meta key")
    if is_manual_request(request):
        return "http"
    return _validate_mode(
        settings.get("ZYTE_API_MODE", "auto"), source="the ZYTE_API_MODE setting"
    )


def _resolve_auto_mode(
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


def _resolve_mode(
    request: Request, api_params: dict[str, Any], settings: Settings, auth_type: str
) -> tuple[str, str]:
    """Returns (assigned_mode, effective_mode).

    assigned_mode is "auto", "proxy", or "http".
    effective_mode is "proxy" or "http" — "auto" is resolved based on request
    data.
    """
    assigned_mode = _get_assigned_mode(request, settings)
    if assigned_mode != "auto":
        return assigned_mode, assigned_mode
    return "auto", _resolve_auto_mode(request, api_params, auth_type)
