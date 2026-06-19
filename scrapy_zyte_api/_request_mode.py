from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._proxy import _has_proxy_mode_headers, _is_proxy_mode_compatible
from ._request_type import is_manual_request

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.settings import Settings


def _get_assigned_mode(request: Request, settings: Settings) -> str:
    """Returns "auto", "http" or "proxy", whichever the request is supposed to
    use."""
    return request.meta.get(
        "zyte_api_mode",
        "http" if is_manual_request(request) else settings.get("ZYTE_API_MODE", "auto"),
    )


def _resolve_auto_mode(
    request: Request, api_params: dict[str, Any], auth_type: str
) -> str:
    return (
        "proxy"
        if auth_type == "zyte"
        and (_has_proxy_mode_headers(request) or _is_proxy_mode_compatible(api_params))
        else "http"
    )


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
