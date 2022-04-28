from base64 import b64decode
from typing import Dict, List, Optional

from scrapy import Request
from scrapy.http import Response, TextResponse


class ZyteAPIMixin:
    def __init__(self, *args, zyte_api_response=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._zyte_api_response = zyte_api_response

    @property
    def zyte_api_response(self):
        return self._zyte_api_response

    @staticmethod
    def _prepare_headers(init_headers: Optional[List[Dict[str, str]]]):
        if not init_headers:
            return None
        return {h["name"]: h["value"] for h in init_headers}


class ZyteAPITextResponse(ZyteAPIMixin, TextResponse):
    @classmethod
    def from_api_response(cls, api_response: Dict, *, request: Request = None):
        return cls(
            url=api_response["url"],
            status=200,
            body=api_response["browserHtml"].encode("utf-8"),
            request=request,
            flags=["zyte-api"],
            headers=cls._prepare_headers(api_response.get("httpResponseHeaders")),
            zyte_api_response=api_response,
        )


class ZyteAPIResponse(ZyteAPIMixin, Response):
    @classmethod
    def from_api_response(cls, api_response: Dict, *, request: Request = None):
        return cls(
            url=api_response["url"],
            status=200,
            body=b64decode(api_response["httpResponseBody"]),
            request=request,
            flags=["zyte-api"],
            headers=cls._prepare_headers(api_response.get("httpResponseHeaders")),
            zyte_api_response=api_response,
        )
