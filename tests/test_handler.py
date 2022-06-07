import pytest
from scrapy.utils.reactor import install_reactor
from scrapy.utils.test import get_crawler
from twisted.internet.asyncioreactor import AsyncioSelectorReactor
from zyte_api.aio.client import AsyncClient

from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler


_API_KEY = 'a'

_BASE_SETTINGS = {
    'DOWNLOAD_HANDLERS': {
        'http': 'scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler',
        'https': 'scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler'
    },
    'ZYTE_API_KEY': _API_KEY,
    'TWISTED_REACTOR': AsyncioSelectorReactor,
}
_DEFAULT_CLIENT_CONCURRENCY = AsyncClient(api_key=_API_KEY).n_conn


@pytest.mark.parametrize(
    'concurrency',
    (
        1,
        _DEFAULT_CLIENT_CONCURRENCY,
        _DEFAULT_CLIENT_CONCURRENCY + 1,
    ),
)
def test_concurrency(concurrency):
    settings = {
        **_BASE_SETTINGS,
        'CONCURRENT_REQUESTS': concurrency,
    }
    crawler = get_crawler(settings_dict=settings)
    handler = ScrapyZyteAPIDownloadHandler(
        settings=crawler.settings,
        crawler=crawler,
    )
    assert handler._client.n_conn == concurrency
    assert handler._session.connector.limit == concurrency
