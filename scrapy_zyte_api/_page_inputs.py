from base64 import b64decode
from typing import Any

import attrs

from ._annotations import _ActionResult


@attrs.define
class Actions:
    """A page input that specifies browser actions and contains their results.

    The actions must be :ref:`specified with an annotation
    <browser-actions>` using :func:`~scrapy_zyte_api.actions`.
    """

    #: Results of actions.
    results: list[_ActionResult] | None


@attrs.define
class Geolocation:
    """A page input that forces a given geolocation for all other page inputs.

    The target geolocation must be :ref:`specified with an annotation
    <geolocation>`.
    """


@attrs.define
class Screenshot:
    """A container for holding the screenshot of a webpage."""

    #: Body.
    body: bytes

    @classmethod
    def from_base64(cls, body):
        return cls(body=b64decode(body.encode()))


@attrs.define
class CapturedResponse:
    """A network response captured during browser page rendering.

    Part of :class:`NetworkCapture`.
    """

    #: Response URL.
    url: str

    #: HTTP status code.
    status: int

    #: Response headers.
    headers: dict[str, str]

    #: Response body. ``None`` if ``httpResponseBody`` was not set to ``True``
    #: on the matching filter.
    body: bytes | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapturedResponse":
        body_b64: str | None = data.get("httpResponseBody")
        return cls(
            url=data["url"],
            status=data["statusCode"],
            headers=data.get("headers", {}),
            body=b64decode(body_b64) if body_b64 is not None else None,
        )


@attrs.define
class NetworkCapture:
    """A page input that specifies network capture filters and contains captured responses.

    The filters must be :ref:`specified with an annotation
    <network-capture>` using :func:`~scrapy_zyte_api.network_capture`.
    """

    #: Captured responses.
    results: list[CapturedResponse]
