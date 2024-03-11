from enum import Enum


class ExtractFrom(str, Enum):
    httpResponseBody: str = "httpResponseBody"
    browserHtml: str = "browserHtml"
