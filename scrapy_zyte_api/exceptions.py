from typing import Union

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
        self.response: Union[ZyteAPIResponse, ZyteAPITextResponse] = response
