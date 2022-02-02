## Requirements

* scrapy>=2.5.1
* zyte-api>=0.1.2
* twisted>=21.7.0

If you are deploying on Scrapy Cloud, then add the below packages to your requirements.txt file.

* zyte-api>=0.1.2
* twisted>=21.7.0
* git+https://github.com/scrapy-plugins/scrapy-zyte-api.git

## Installation

It is not yet available on PyPI. However, it can be installed directly from GitHub:

`pip install git+ssh://git@github.com/scrapy-plugins/scrapy-zyte-api.git`

or

`pip install git+https://github.com/scrapy-plugins/scrapy-zyte-api.git`

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
                       "browserHtml": True,
                       "geolocation": "US",
                       "javascript": True,
                       "echoData": {"something": True}
                   }
               }),
```

## Example Code:

```python
import scrapy
import os


class TestSpider(scrapy.Spider):
    name = 'test'
    os.environ["ZYTE_API_KEY"] = "<You ZYTE_API_KEY>"
    start_urls = ['http://books.toscrape.com/']

    def start_requests(self):

            yield scrapy.Request(url="http://books.toscrape.com/", callback=self.parse,
                                 meta={
                                     "zyte_api": {
                                         "browserHtml": True,
                                         # You can set any GEOLocation region you want.
                                         "geolocation": "US",
                                         "javascript": True,
                                         "echoData": {"something": True}
                                     }
                                 })

    def parse(self, response, **kwargs):
        yield{
            'URL': response.url,
            'status': response.status,
            'HTML': response.body
        }
```