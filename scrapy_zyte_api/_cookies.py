from http.cookiejar import Cookie
from typing import Any, Dict, List

from scrapy.http import Request
from scrapy.http.cookies import CookieJar


def _get_cookie_jar(request: Request, cookie_jars: Dict[Any, CookieJar]) -> CookieJar:
    jar_id = request.meta.get("cookiejar")
    return cookie_jars[jar_id]


def _process_cookies(
    api_response: Dict[str, Any], request: Request, cookie_jars: Dict[Any, CookieJar]
):
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
            domain=response_cookie["domain"],
            domain_specified=True,
            domain_initial_dot=response_cookie["domain"].startswith("."),
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
    request: Request, cookie_jars: Dict[Any, CookieJar]
) -> List[Cookie]:
    cookie_jar = _get_cookie_jar(request, cookie_jars)
    return list(cookie_jar.jar)
