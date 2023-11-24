.. _scrapy-poet-setup:

=================
scrapy-poet setup
=================

For :ref:`scrapy-poet integration <scrapy-poet>`:

-   Install or reinstall ``scrapy-zyte-api`` with the ``provider`` extra to
    install additional required dependencies:

    .. code-block:: shell

        pip install scrapy-zyte-api[provider]

-   Add the following provider to the ``SCRAPY_POET_PROVIDERS`` setting:

    .. code-block:: python

        SCRAPY_POET_PROVIDERS = {
            "scrapy_zyte_api.providers.ZyteApiProvider": 1100,
        }

You can now :ref:`use scrapy-poet <scrapy-poet>` to get data from Zyte API in
page objects.
