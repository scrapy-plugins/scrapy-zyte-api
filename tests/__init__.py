from contextlib import asynccontextmanager

from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from zyte_api.aio.client import AsyncClient


@asynccontextmanager
async def make_handler(settings_dict: dict, api_url: str):
    from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler

    crawler = get_crawler(settings_dict=settings_dict)
    handler = ScrapyZyteAPIDownloadHandler(
        Settings(settings_dict), crawler=crawler, client=AsyncClient(api_url=api_url)
    )
    # TODO Close handler if needed
    yield handler
