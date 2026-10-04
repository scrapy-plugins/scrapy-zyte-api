from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .responses import ZyteAPIResponse, ZyteAPITextResponse


class ActionError(ValueError):
    """Exception raised when a Zyte API response contains an action error."""

    def __init__(self, response, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #: Offending Zyte API response.
        #:
        #: You can inspect the outcome of actions in the ``"actions"`` key of
        #: :attr:`response.raw_api_response
        #: <scrapy_zyte_api.responses.ZyteAPITextResponse.raw_api_response>`.
        self.response: ZyteAPIResponse | ZyteAPITextResponse = response
