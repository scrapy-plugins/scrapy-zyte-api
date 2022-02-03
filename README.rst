===============
scrapy-zyte-api
===============

.. image:: https://img.shields.io/pypi/v/scrapy-zyte-api.svg
   :target: https://pypi.python.org/pypi/scrapy-zyte-api
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/scrapy-zyte-api.svg
   :target: https://pypi.python.org/pypi/scrapy-zyte-api
   :alt: Supported Python Versions

.. image:: https://github.com/scrapy-plugins/scrapy-zyte-api/actions/workflows/test.yml/badge.svg
   :target: https://github.com/scrapy-plugins/scrapy-zyte-api/actions/workflows/test.yml
   :alt: Automated tests

.. image:: https://codecov.io/github/scrapinghub/scrapy-zyte-api/coverage.svg?branch=master
   :target: https://codecov.io/gh/scrapinghub/scrapy-zyte-api
   :alt: Coverage report

Installation
------------

.. code-block::

    pip install scrapy-zyte-api

This package requires Python 3.7+.

How to configure
----------------

Replace the default ``http`` and ``https`` in Scrapy's
`DOWNLOAD_HANDLERS <https://docs.scrapy.org/en/latest/topics/settings.html>`_
in the ``settings.py`` of your Scrapy project.

You also need to set the ``ZYTE_API_KEY``.

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler"
    }

    # Having the following in the env var would also work.
    ZYTE_API_KEY = "<your API key>"

Also, make sure to `install the asyncio-based Twisted reactor
<https://docs.scrapy.org/en/latest/topics/asyncio.html#installing-the-asyncio-reactor)>`_
in the ``settings.py`` file as well:

.. code-block:: python

    TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

How to use
----------

Set the ``zyte_api`` `Request.meta
<https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
key to download a request using Zyte API. Full list of parameters is provided in the
`Zyte API Specification <https://docs.zyte.com/zyte-api/openapi.html#zyte-openapi-spec>`_.

.. code-block:: python

    yield scrapy.Request(
        "http://books.toscrape.com/",
        callback=self.parse,
        meta={
            "zyte_api": {
                "browserHtml": True,
                "geolocation": "US",
                "javascript": True,
                "echoData": {"something": True}
            }
        }
    )
