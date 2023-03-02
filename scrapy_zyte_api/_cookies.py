from typing import Any, Dict

from scrapy.http import Request
from scrapy.http.cookies import CookieJar


def _get_all_cookies(request: Request, cookie_jars: Dict[Any, CookieJar]):
    jar_id = request.meta.get("cookiejar")
    cookie_jar = cookie_jars.get(jar_id)
    if cookie_jar is None:
        return []
    return list(cookie_jar.jar)
