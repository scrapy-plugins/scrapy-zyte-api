from .utils import _NEEDS_EARLY_REACTOR

if _NEEDS_EARLY_REACTOR:
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from ._annotations import ExtractFrom, actions
from ._middlewares import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)
from ._page_inputs import Actions, Geolocation, Screenshot
from ._request_fingerprinter import ScrapyZyteAPIRequestFingerprinter
from ._session import (
    SESSION_AGGRESSIVE_RETRY_POLICY as _SESSION_AGGRESSIVE_RETRY_POLICY,
)
from ._session import SESSION_DEFAULT_RETRY_POLICY as _SESSION_DEFAULT_RETRY_POLICY
from ._session import (
    ScrapyZyteAPISessionDownloaderMiddleware,
    SessionConfig,
    session_config,
)
from .addon import Addon
from .handler import ScrapyZyteAPIDownloadHandler

# We re-define the variables here for Sphinx to pick the documentation.

#: Alternative to the :ref:`default retry policy <default-retry-policy>` for
#: :ref:`session management <session>` that does not retry 520 responses.
SESSION_DEFAULT_RETRY_POLICY = _SESSION_DEFAULT_RETRY_POLICY

#: Alternative to the :ref:`aggresive retry policy <aggressive-retry-policy>`
#: for :ref:`session management <session>` that does not retry 520 and 521
#: responses.
#:
#: .. note:: When using python-zyte-api 0.5.2 or lower, this is the same as
#:           :data:`~scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY`.
SESSION_AGGRESSIVE_RETRY_POLICY = _SESSION_AGGRESSIVE_RETRY_POLICY
