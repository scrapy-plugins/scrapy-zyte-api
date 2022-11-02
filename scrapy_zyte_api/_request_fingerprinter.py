from typing import TYPE_CHECKING

try:
    from scrapy.utils.request import RequestFingerprinter  # NOQA
except ImportError:
    if not TYPE_CHECKING:
        ScrapyZyteAPIRequestFingerprinter = None
else:
    import hashlib
    import json
    from weakref import WeakKeyDictionary

    from scrapy import Request
    from scrapy.settings.default_settings import REQUEST_FINGERPRINTER_CLASS
    from scrapy.utils.misc import create_instance, load_object
    from w3lib.url import canonicalize_url

    from ._params import (
        _get_api_params,
        _load_browser_headers,
        _load_default_params,
        _load_skip_headers,
    )

    class ScrapyZyteAPIRequestFingerprinter:
        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        def __init__(self, crawler):
            settings = crawler.settings
            self._automap_params = _load_default_params(
                settings, "ZYTE_API_AUTOMAP_PARAMS"
            )
            self._browser_headers = _load_browser_headers(settings)
            self._default_params = _load_default_params(
                settings, "ZYTE_API_DEFAULT_PARAMS"
            )
            self._transparent_mode = settings.getbool(
                "ZYTE_API_TRANSPARENT_MODE", False
            )
            self._skip_headers = _load_skip_headers(settings)
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
            self._cache: "WeakKeyDictionary[Request, bytes]"
            self._cache = WeakKeyDictionary()
            self._skip_keys = (
                "customHttpRequestHeaders",
                "echoData",
                "jobId",
                "requestHeaders",
            )

        def _keep_fragments(self, api_params):
            return any(
                api_params.get(key, False) for key in ("browserHtml", "screenshot")
            )

        def fingerprint(self, request):
            if request in self._cache:
                return self._cache[request]
            api_params = _get_api_params(
                request,
                default_params=self._default_params,
                transparent_mode=self._transparent_mode,
                automap_params=self._automap_params,
                skip_headers=self._skip_headers,
                browser_headers=self._browser_headers,
                job_id=None,
            )
            if api_params is not None:
                api_params["url"] = canonicalize_url(
                    api_params["url"],
                    keep_fragments=self._keep_fragments(api_params),
                )
                for key in self._skip_keys:
                    api_params.pop(key, None)
                fingerprint_json = json.dumps(api_params, sort_keys=True)
                self._cache[request] = hashlib.sha1(fingerprint_json.encode()).digest()
                return self._cache[request]
            return self._fallback_request_fingerprinter.fingerprint(request)
