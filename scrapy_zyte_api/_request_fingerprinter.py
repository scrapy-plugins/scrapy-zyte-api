from logging import getLogger
from typing import TYPE_CHECKING, cast

logger = getLogger(__name__)

try:  # noqa: C901
    from scrapy.utils.request import RequestFingerprinter as _  # noqa: F401
except ImportError:
    if not TYPE_CHECKING:
        ScrapyZyteAPIRequestFingerprinter = None
else:
    import hashlib
    import json
    from base64 import b64encode
    from weakref import WeakKeyDictionary

    from scrapy import Request
    from scrapy.settings.default_settings import (
        REQUEST_FINGERPRINTER_CLASS as ScrapyRequestFingerprinter,
    )
    from scrapy.utils.misc import load_object
    from w3lib.url import canonicalize_url

    from ._params import _REQUEST_PARAMS, _ParamParser, _uses_browser
    from .utils import _build_from_crawler

    class ScrapyZyteAPIRequestFingerprinter:
        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        def __init__(self, crawler):
            settings = crawler.settings
            try:
                from scrapy_poet import ScrapyPoetRequestFingerprinter
            except ImportError:
                self._has_poet = False
                RequestFingerprinter = ScrapyRequestFingerprinter
            else:
                self._has_poet = True
                RequestFingerprinter = ScrapyPoetRequestFingerprinter
            self._fallback_request_fingerprinter = _build_from_crawler(
                load_object(
                    settings.get(
                        "ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS",
                        RequestFingerprinter,
                    )
                ),
                crawler,
            )
            if self._has_poet and not isinstance(
                self._fallback_request_fingerprinter, cast(type, RequestFingerprinter)
            ):
                logger.warning(
                    f"You have scrapy-poet installed, but your custom value "
                    f"for the ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS "
                    f"setting "
                    f"({settings['ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS']!r})"
                    f" does not point to a subclass of "
                    f"scrapy_poet.ScrapyPoetRequestFingerprinter. For request "
                    f"fingerprinting to work properly, consider switching "
                    f"ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS to "
                    f"scrapy_poet.ScrapyPoetRequestFingerprinter or a "
                    f"subclass. You can move your current value of the "
                    f"ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS setting "
                    f"to the SCRAPY_POET_REQUEST_FINGERPRINTER_BASE_CLASS "
                    f"setting instead."
                )
                self._has_poet = False
            self._cache: "WeakKeyDictionary[Request, bytes]" = WeakKeyDictionary()
            self._param_parser = _ParamParser(crawler, cookies_enabled=False)

        def _normalize_params(self, api_params):
            api_params["url"] = canonicalize_url(
                api_params["url"],
                keep_fragments=_uses_browser(api_params),
            )

            if "httpRequestText" in api_params:
                api_params["httpRequestBody"] = b64encode(
                    api_params.pop("httpRequestText").encode()
                ).decode()

            for key, value in _REQUEST_PARAMS.items():
                if value["changes_fingerprint"] is False:
                    api_params.pop(key, None)

        def fingerprint(self, request):
            if request in self._cache:
                return self._cache[request]
            api_params = self._param_parser.parse(request)
            if api_params is not None:
                self._normalize_params(api_params)
                fingerprint = json.dumps(api_params, sort_keys=True).encode()
                if self._has_poet:
                    deps_key = self._fallback_request_fingerprinter.get_deps_key(
                        request
                    )
                    serialized_page_params = (
                        self._fallback_request_fingerprinter.serialize_page_params(
                            request
                        )
                    )
                    if deps_key is not None:
                        fingerprint += deps_key
                    if serialized_page_params is not None:
                        fingerprint += serialized_page_params
                self._cache[request] = hashlib.sha1(fingerprint).digest()
                return self._cache[request]
            return self._fallback_request_fingerprinter.fingerprint(request)
