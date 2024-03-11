import attrs
from web_poet import Injectable


@attrs.define
class Screenshot(Injectable):
    """A container for holding the screenshot of a webpage."""

    body: bytes
