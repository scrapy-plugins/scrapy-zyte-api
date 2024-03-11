import attrs


@attrs.define
class Screenshot:
    """A container for holding the screenshot of a webpage."""

    body: bytes
