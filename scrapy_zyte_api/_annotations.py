from enum import Enum

import attrs


class ExtractFrom(str, Enum):
    httpResponseBody: str = "httpResponseBody"
    browserHtml: str = "browserHtml"


class Geolocation:
    pass


@attrs.define
class Screenshot:
    """A container for holding the screenshot of a webpage."""

    body: bytes
