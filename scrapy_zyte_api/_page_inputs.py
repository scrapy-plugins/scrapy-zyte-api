from base64 import b64decode

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
