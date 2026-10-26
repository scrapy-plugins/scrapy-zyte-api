from contextlib import suppress
from email.utils import parsedate_to_datetime
from http.cookiejar import Cookie
from typing import Any
from urllib.parse import urlparse

from scrapy.http import Request
from scrapy.http.cookies import CookieJar


def _parse_set_cookie_header(header_value: str) -> dict | None:
    parts = [p.strip() for p in header_value.split(";")]
    if not parts or "=" not in parts[0]:
        return None
    name, _, value = parts[0].partition("=")
    result: dict = {"name": name.strip(), "value": value.strip()}
    for part in parts[1:]:
        if "=" in part:
            key, _, val = part.partition("=")
            key_lower = key.strip().lower()
            val = val.strip()
        else:
            key_lower = part.strip().lower()
            val = ""
        if key_lower == "domain":
            result["domain"] = val
        elif key_lower == "path":
            result["path"] = val
        elif key_lower == "expires" and val:
            with suppress(Exception):
                result["expires"] = int(parsedate_to_datetime(val).timestamp())
        elif key_lower == "httponly":
            result["httpOnly"] = True
        elif key_lower == "secure":
            result["secure"] = True
        elif key_lower == "samesite" and val:
            result["sameSite"] = val
    return result


def _get_cookie_jar(request: Request, cookie_jars: dict[Any, CookieJar]) -> CookieJar:
    jar_id = request.meta.get("cookiejar")
    return cookie_jars[jar_id]


def _get_cookie_domain(cookie, url):
    domain = cookie.get("domain")
    if domain:
        return domain
    domain = urlparse(url).hostname
    if domain:
        return domain
    raise ValueError(
        f"Got a cookie without a domain from URL {url} which has no domain either."
    )


def _process_cookies(
    api_response: dict[str, Any],
    request: Request,
    cookie_jars: dict[Any, CookieJar] | None,
):
    if not cookie_jars:
        return
    response_cookies = api_response.get("experimental", {}).get("responseCookies")
    if not response_cookies:
        return
    cookie_jar = _get_cookie_jar(request, cookie_jars)
    for response_cookie in response_cookies:
        rest = {}
        http_only = response_cookie.get("httpOnly", None)
        if http_only is not None:
            rest["httpOnly"] = http_only
        same_site = response_cookie.get("sameSite", None)
        if same_site is not None:
            rest["sameSite"] = same_site
        cookie = Cookie(
            version=1,
            name=response_cookie["name"],
            value=response_cookie["value"],
            port=None,
            port_specified=False,
            domain=_get_cookie_domain(response_cookie, api_response["url"]),
            domain_specified="domain" in response_cookie,
            domain_initial_dot=response_cookie.get("domain", "").startswith("."),
            path=response_cookie.get("path", "/"),
            path_specified="path" in response_cookie,
            secure=response_cookie.get("secure", False),
            expires=response_cookie.get("expires", None),
            discard=False,
            comment=None,
            comment_url=None,
            rest=rest,
        )
        cookie_jar.set_cookie(cookie)


def _get_all_cookies(
    request: Request, cookie_jars: dict[Any, CookieJar]
) -> list[Cookie]:
    cookie_jar = _get_cookie_jar(request, cookie_jars)
    return list(cookie_jar.jar)
