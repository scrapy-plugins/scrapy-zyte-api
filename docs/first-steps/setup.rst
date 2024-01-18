.. _setup:

=============
Initial setup
=============

Learn how to get scrapy-zyte-api installed and configured on an existing
:doc:`Scrapy <scrapy:index>` project.

.. tip:: :ref:`Zyte’s web scraping tutorial <zyte:tutorial>` covers
    scrapy-zyte-api setup as well.

Requirements
============

You need at least:

-   A :ref:`Zyte API <zyte-api>` subscription (there’s a :ref:`free trial
    <zyte-api-trial>`).

-   Python 3.7+

-   Scrapy 2.0.1+

:doc:`scrapy-poet <scrapy-poet:index>` integration requires higher versions:

-   Python 3.8+

-   Scrapy 2.6+


Installation
============

.. code-block:: shell

    pip install scrapy-zyte-api


Configuration
=============

Add your `Zyte API key`_, and add it to your project ``settings.py``:

.. _Zyte API key: https://app.zyte.com/o/zyte-api/api-access

.. code-block:: python

    ZYTE_API_KEY = "YOUR_API_KEY"

Alternatively, you can set your API key in the ``ZYTE_API_KEY`` environment
variable instead.

Then, set up scrapy-zyte-api integration in ``settings.py``:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "http": "scrapy_zyte_api.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.ScrapyZyteAPIDownloadHandler",
    }
    DOWNLOADER_MIDDLEWARES = {
        "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 1000,
    }
    REQUEST_FINGERPRINTER_CLASS = "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter"
    SPIDER_MIDDLEWARES = {
        "scrapy_zyte_api.ScrapyZyteAPISpiderMiddleware": 100,
    }
    TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

By default, scrapy-zyte-api doesn't change the spider behavior. To switch your
spider to use Zyte API for all requests, set the following setting as well:

.. code-block:: python

    ZYTE_API_TRANSPARENT_MODE = True

If you already had a custom value for :setting:`REQUEST_FINGERPRINTER_CLASS
<scrapy:REQUEST_FINGERPRINTER_CLASS>`, set that value on
:ref:`ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS` instead.

If you had a different value for :setting:`TWISTED_REACTOR
<scrapy:TWISTED_REACTOR>` or no value at all, you will be changing the Twisted
reactor that your Scrapy project uses, and your existing code may need changes,
such as:

-   :ref:`asyncio-preinstalled-reactor`.

    Some Twisted imports install the default, non-asyncio Twisted
    reactor as a side effect. Once a reactor is installed, it cannot be
    changed for the whole run time.

-   :ref:`asyncio-await-dfd`.

    Note that you might be using Deferreds without realizing it through
    some Scrapy functions and methods. For example, when you yield the
    return value of ``self.crawler.engine.download()`` from a spider
    callback, you are yielding a Deferred.
