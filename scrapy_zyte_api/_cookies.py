from scrapy.http import Request
from scrapy.http.cookies import CookieJar, potential_domain_matches
from scrapy.utils.httpobj import urlparse_cached


def _get_all_cookies(cookie_jar: CookieJar):
    if cookie_jar is None:
        return []
    return list(cookie_jar.jar)


def _get_request_cookies(cookie_jar: CookieJar, request: Request):
    if cookie_jar is None:
        return []
    cookies = []
    domain = urlparse_cached(request).hostname
    matching_domains = potential_domain_matches(domain)
    for cookie in cookie_jar.jar:
        if cookie.domain in matching_domains:
            cookies.append(cookie)
    return cookies
