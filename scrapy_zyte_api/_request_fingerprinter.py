from typing import TYPE_CHECKING

try:
    from scrapy.utils.request import RequestFingerprinter  # NOQA
except ImportError:
    if not TYPE_CHECKING:
        ScrapyZyteAPIRequestFingerprinter = None
else:
    import hashlib
    import json
    from base64 import b64encode
    from weakref import WeakKeyDictionary

    from scrapy import Request
    from scrapy.settings.default_settings import REQUEST_FINGERPRINTER_CLASS
    from scrapy.utils.misc import create_instance, load_object
    from w3lib.url import canonicalize_url

    from ._params import _REQUEST_PARAMS, _ParamParser, _uses_browser

    class ScrapyZyteAPIRequestFingerprinter:
        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        def __init__(self, crawler):
            settings = crawler.settings
            self._fallback_request_fingerprinter = create_instance(
                load_object(
                    settings.get(
                        "ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS",
                        REQUEST_FINGERPRINTER_CLASS,
                    )
                ),
                settings=crawler.settings,
                crawler=crawler,
            )
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
                fingerprint_json = json.dumps(api_params, sort_keys=True)
                self._cache[request] = hashlib.sha1(fingerprint_json.encode()).digest()
                return self._cache[request]
            return self._fallback_request_fingerprinter.fingerprint(request)
