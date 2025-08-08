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
    <zapi-trial>`).

-   Python 3.9+

-   Scrapy 2.0.1+

:doc:`scrapy-poet <scrapy-poet:index>` integration requires Scrapy 2.6+.

:ref:`x402 support <x402>` requires Python 3.10+.


.. _install:

Installation
============

For a basic installation:

.. code-block:: shell

    pip install scrapy-zyte-api

For :ref:`scrapy-poet integration <scrapy-poet>`:

.. code-block:: shell

    pip install scrapy-zyte-api[provider]

For :ref:`x402 support <x402>`, make sure you have Python 3.10+ and install
the ``x402`` extra:

.. code-block:: shell

    pip install scrapy-zyte-api[x402]

Note that you can install multiple extras_:

.. _extras: https://setuptools.pypa.io/en/latest/userguide/dependency_management.html#optional-dependencies

.. code-block:: shell

    pip install scrapy-zyte-api[provider,x402]


Configuration
=============

To configure scrapy-zyte-api, :ref:`set up authentication <auth>` and either
:ref:`enable the add-on <config-addon>` (Scrapy ≥ 2.10) or :ref:`configure all
components separately <config-components>`.

.. warning:: :ref:`reactor-change`.

.. _auth:
.. _config-api-key:

Authentication
--------------

`Sign up for a Zyte API account
<https://app.zyte.com/account/signup/zyteapi>`_, copy `your API key
<https://app.zyte.com/o/zyte-api/api-access>`_ and do either of the following:

-   Define an environment variable named ``ZYTE_API_KEY`` with your API key:

    -   On Windows’ CMD:

        .. code-block:: shell

                > set ZYTE_API_KEY=YOUR_API_KEY

    -   On macOS and Linux:

        .. code-block:: shell

                $ export ZYTE_API_KEY=YOUR_API_KEY

-   Add your API key to your setting module:

    .. code-block:: python
        :caption: settings.py

        ZYTE_API_KEY = "YOUR_API_KEY"

To use `x402 <https://www.x402.org/>`__ instead, see :ref:`x402`.


.. _config-addon:

Enabling the add-on
-------------------

If you are using Scrapy 2.10 or higher, you can set up scrapy-zyte-api
integration using the following :ref:`add-on <topics-addons>` with any
priority:

.. code-block:: python
    :caption: settings.py

    ADDONS = {
        "scrapy_zyte_api.Addon": 500,
    }

.. note:: The addon enables :ref:`transparent mode <transparent>` by default.


.. _config-components:

Enabling all components separately
----------------------------------

If :ref:`enabling the add-on <config-addon>` is not an option, you can set up
scrapy-zyte-api integration as follows:

.. code-block:: python
    :caption: settings.py

    DOWNLOAD_HANDLERS = {
        "http": "scrapy_zyte_api.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.ScrapyZyteAPIDownloadHandler",
    }
    DOWNLOADER_MIDDLEWARES = {
        "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
    }
    SPIDER_MIDDLEWARES = {
        "scrapy_zyte_api.ScrapyZyteAPISpiderMiddleware": 100,
        "scrapy_zyte_api.ScrapyZyteAPIRefererSpiderMiddleware": 1000,
    }
    REQUEST_FINGERPRINTER_CLASS = "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter"
    TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

By default, scrapy-zyte-api doesn't change the spider behavior. To switch your
spider to use Zyte API for all requests, set the following setting as well:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_TRANSPARENT_MODE = True

For :ref:`scrapy-poet integration <scrapy-poet>`, :ref:`configure scrapy-poet
<scrapy-poet:setup>` first, and then add the following provider to the
``SCRAPY_POET_PROVIDERS`` setting:

.. code-block:: python
    :caption: settings.py

    SCRAPY_POET_PROVIDERS = {
        "scrapy_zyte_api.providers.ZyteApiProvider": 1100,
    }

If you already had a custom value for :setting:`REQUEST_FINGERPRINTER_CLASS
<scrapy:REQUEST_FINGERPRINTER_CLASS>`, set that value on
:setting:`ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS` instead.

.. code-block:: python
    :caption: settings.py

    ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS = "myproject.CustomRequestFingerprinter"

For :ref:`session management support <session>`, add the following downloader
middleware to the :setting:`DOWNLOADER_MIDDLEWARES
<scrapy:DOWNLOADER_MIDDLEWARES>` setting:

.. code-block:: python
    :caption: settings.py

    DOWNLOADER_MIDDLEWARES = {
        "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
    }


.. _reactor-change:

Changing reactors may require code changes
==========================================

If your :setting:`TWISTED_REACTOR <scrapy:TWISTED_REACTOR>` setting was not
set to ``"twisted.internet.asyncioreactor.AsyncioSelectorReactor"`` before,
you will be changing the Twisted reactor that your Scrapy project uses, and
your existing code may need changes, such as:

-   :ref:`asyncio-preinstalled-reactor`.

    Some Twisted imports install the default, non-asyncio Twisted
    reactor as a side effect. Once a reactor is installed, it cannot be
    changed for the whole run time.

-   :ref:`asyncio-await-dfd`.

    Note that you might be using Deferreds without realizing it through
    some Scrapy functions and methods. For example, when you yield the
    return value of ``self.crawler.engine.download()`` from a spider
    callback, you are yielding a Deferred.


.. _x402:

x402
====

It is possible to use :ref:`Zyte API <zyte-api>` without a Zyte API account by 
using the `x402 <https://www.x402.org/>`__ protocol to handle payments:

#.  Read the `Zyte Terms of Service`_. By using Zyte API, you are accepting
    them.

    .. _Zyte Terms of Service: https://www.zyte.com/terms-policies/terms-of-service/

#.  During :ref:`installation <install>`, make sure to install the ``x402``
    extra.

#.  :ref:`Configure <eth-key>` the *private* key of your Ethereum_ account to
    authorize payments.

    .. _Ethereum: https://ethereum.org/

.. _eth-key:

Configuring your Ethereum private key
-------------------------------------

It is recommended to configure your Ethereum private key through an environment
variable, so that it also works when you use :doc:`python-zyte-api
<python-zyte-api:index>`:

-  On Windows’ CMD:

   .. code-block:: shell

        > set ZYTE_API_ETH_KEY=YOUR_ETH_PRIVATE_KEY

-  On macOS and Linux:

   .. code-block:: shell

        $ export ZYTE_API_ETH_KEY=YOUR_ETH_PRIVATE_KEY

Alternatively, you can add your Ethereum private key to the settings module:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_ETH_KEY = "YOUR_ETH_PRIVATE_KEY"
