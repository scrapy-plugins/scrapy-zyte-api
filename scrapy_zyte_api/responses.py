from base64 import b64decode
from typing import Dict, List, Optional, Tuple, Union

from scrapy import Request
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes

_DEFAULT_ENCODING = "utf-8"


class ZyteAPIMixin:

    REMOVE_HEADERS = {
        # Zyte API already decompresses the HTTP Response Body. Scrapy's
        # HttpCompressionMiddleware will error out when it attempts to
        # decompress an already decompressed body based on this header.
        "content-encoding"
    }

    def __init__(self, *args, raw_api_response: Dict = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._raw_api_response = raw_api_response

    def replace(self, *args, **kwargs):
        if kwargs.get("raw_api_response"):
            raise ValueError("Replacing the value of 'raw_api_response' isn't allowed.")
        return super().replace(*args, **kwargs)

    @property
    def raw_api_response(self) -> Optional[Dict]:
        """Contains the raw API response from Zyte API.

        To see the full list of parameters and their description, kindly refer to the
        `Zyte API Specification <https://docs.zyte.com/zyte-api/openapi.html#zyte-openapi-spec>`_.
        """
        return self._raw_api_response

    @classmethod
    def _prepare_headers(cls, init_headers: Optional[List[Dict[str, str]]]):
        if not init_headers:
            return None
        return {
            h["name"]: h["value"]
            for h in init_headers
            if h["name"].lower() not in cls.REMOVE_HEADERS
        }


class ZyteAPITextResponse(ZyteAPIMixin, TextResponse):

    attributes: Tuple[str, ...] = TextResponse.attributes + ("raw_api_response",)

    @classmethod
    def from_api_response(cls, api_response: Dict, *, request: Request = None):
        """Alternative constructor to instantiate the response from the raw
        Zyte API response.
        """
        body = None
        encoding = None

        if api_response.get("browserHtml"):
            encoding = _DEFAULT_ENCODING  # Zyte API has "utf-8" by default
            body = api_response["browserHtml"].encode(encoding)
        elif api_response.get("httpResponseBody"):
            body = b64decode(api_response["httpResponseBody"])

        return cls(
            url=api_response["url"],
            status=api_response.get("statusCode") or 200,
            body=body,
            encoding=encoding,
            request=request,
            flags=["zyte-api"],
            headers=cls._prepare_headers(api_response.get("httpResponseHeaders")),
            raw_api_response=api_response,
        )


class ZyteAPIResponse(ZyteAPIMixin, Response):

    attributes: Tuple[str, ...] = Response.attributes + ("raw_api_response",)

    @classmethod
    def from_api_response(cls, api_response: Dict, *, request: Request = None):
        """Alternative constructor to instantiate the response from the raw
        Zyte API response.
        """
        return cls(
            url=api_response["url"],
            status=api_response.get("statusCode") or 200,
            body=b64decode(api_response.get("httpResponseBody") or ""),
            request=request,
            flags=["zyte-api"],
            headers=cls._prepare_headers(api_response.get("httpResponseHeaders")),
            raw_api_response=api_response,
        )


def _process_response(
    api_response: Dict[str, Union[List[Dict], str]], request: Request
) -> Optional[Union[ZyteAPITextResponse, ZyteAPIResponse]]:
    """Given a Zyte API Response and the ``scrapy.Request`` that asked for it,
    this returns either a ``ZyteAPITextResponse`` or ``ZyteAPIResponse`` depending
    on which if it can properly decode the HTTP Body or have access to browserHtml.
    """

    # NOTES: Currently, Zyte API does NOT only allow both 'browserHtml' and
    # 'httpResponseBody' to be present at the same time. The support for both
    # will be addressed in the future. Reference:
    # - https://github.com/scrapy-plugins/scrapy-zyte-api/pull/10#issuecomment-1131406460
    # For now, at least one of them should be present.

    if api_response.get("browserHtml"):
        # Using TextResponse because browserHtml always returns a browser-rendered page
        # even when requesting files (like images)
        return ZyteAPITextResponse.from_api_response(api_response, request=request)

    if api_response.get("httpResponseHeaders") and api_response.get("httpResponseBody"):
        response_cls = responsetypes.from_args(
            headers=api_response["httpResponseHeaders"],
            url=api_response["url"],
            # FIXME: update this when python-zyte-api supports base64 decoding
            body=b64decode(api_response["httpResponseBody"]),  # type: ignore
        )
        if issubclass(response_cls, TextResponse):
            return ZyteAPITextResponse.from_api_response(api_response, request=request)

    return ZyteAPIResponse.from_api_response(api_response, request=request)
