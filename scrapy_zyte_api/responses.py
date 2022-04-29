from base64 import b64decode
from typing import Dict, List, Optional

from scrapy import Request
from scrapy.http import Response, TextResponse

_ENCODING = "utf-8"


class ZyteAPIMixin:
    def __init__(self, *args, zyte_api_response: Dict = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._zyte_api_response = zyte_api_response

    def replace(self, *args, **kwargs):
        """Create a new response with the same attributes except for those given
        new values.
        """
        return super().replace(*args, **kwargs)

    @property
    def zyte_api_response(self) -> Optional[Dict]:
        """Contains the raw API response from Zyte API.

        To see the full list of parameters and their description, kindly refer to the
        `Zyte API Specification <https://docs.zyte.com/zyte-api/openapi.html#zyte-openapi-spec>`_.
        """
        return self._zyte_api_response

    @staticmethod
    def _prepare_headers(init_headers: Optional[List[Dict[str, str]]]):
        if not init_headers:
            return None
        return {h["name"]: h["value"] for h in init_headers}


class ZyteAPITextResponse(ZyteAPIMixin, TextResponse):
    @classmethod
    def from_api_response(cls, api_response: Dict, *, request: Request = None):
        """Alternative constructor to instantiate the response from the raw
        Zyte API response.
        """
        return cls(
            url=api_response["url"],
            status=200,
            body=api_response["browserHtml"].encode(_ENCODING),
            encoding=_ENCODING,
            request=request,
            flags=["zyte-api"],
            headers=cls._prepare_headers(api_response.get("httpResponseHeaders")),
            zyte_api_response=api_response,
        )


class ZyteAPIResponse(ZyteAPIMixin, Response):
    @classmethod
    def from_api_response(cls, api_response: Dict, *, request: Request = None):
        """Alternative constructor to instantiate the response from the raw
        Zyte API response.
        """
        return cls(
            url=api_response["url"],
            status=200,
            body=b64decode(api_response["httpResponseBody"]),
            request=request,
            flags=["zyte-api"],
            headers=cls._prepare_headers(api_response.get("httpResponseHeaders")),
            zyte_api_response=api_response,
        )
