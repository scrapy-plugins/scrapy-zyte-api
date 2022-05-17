from contextlib import asynccontextmanager
from typing import Optional

from scrapy.settings import Settings
from scrapy.utils.test import get_crawler
from zyte_api.aio.client import AsyncClient


@asynccontextmanager
async def make_handler(
    settings_dict: dict = {},
    api_url: Optional[str] = None,
    *,
    client: Optional[AsyncClient] = None
):
    from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler

    client = client or AsyncClient(api_url=api_url)
    crawler = get_crawler(settings_dict=settings_dict)
    handler = ScrapyZyteAPIDownloadHandler(
        Settings(settings_dict), crawler=crawler, client=client
    )
    try:
        yield handler
    finally:
        await handler._close()  # NOQA
