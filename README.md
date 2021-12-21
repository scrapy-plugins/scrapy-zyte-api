## How to configure

Replace the default `http` and `https` Download Handlers through [`DOWNLOAD_HANDLERS`](https://docs.scrapy.org/en/latest/topics/settings.html):

```python
DOWNLOAD_HANDLERS = {
    "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
    "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler"
}
```

Also, make sure to [install the `asyncio`-based Twisted reactor](https://docs.scrapy.org/en/latest/topics/asyncio.html#installing-the-asyncio-reactor):

```python
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
```

## How to use

Set the `zyte_api` [Request.meta](https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta) key to download a request using Zyte API. Full list of parameters is provided in the [Zyte API Specification](https://docs.zyte.com/zyte-api/openapi.html#zyte-openapi-spec).

```python
yield scrapy.Request("http://books.toscrape.com/",
               callback=self.parse,
               meta={
                   "zyte_api": {
                       "geolocation": "US",
                       "javascript": True,
                       "echoData": {"something": True}
                   }
               }),
```