from base64 import b64decode

import attrs


class Geolocation:
    """A page input that forces a given geolocation for all other page inputs.

    The target geolocation must be :ref:`specified with an annotation
    <geolocation>`.
    """

    pass


@attrs.define
class Screenshot:
    """A container for holding the screenshot of a webpage."""

    #: Body.
    body: bytes

    @classmethod
    def from_base64(cls, body):
        return cls(body=b64decode(body.encode()))
