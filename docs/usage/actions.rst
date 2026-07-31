.. _actions:

======================
Handling action errors
======================

Even though Zyte API considers a response successful :ref:`even if a browser
action fails <zapi-successful-responses>`, scrapy-zyte-api retries such
responses by default. See :setting:`ZYTE_API_ACTION_ERROR_RETRY_ENABLED`.

You can also use :setting:`ZYTE_API_ACTION_ERROR_HANDLING` to determine how
such responses are handled when they are not retried or when retries are
exceeded: treated as a success (default), ignored, or treated as an error.

.. _action-error-caching:

Action error caching
====================

:class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware` caches
responses before scrapy-zyte-api gets to inspect their actions, so responses
with a failed action are cached regardless of the settings above.
:ref:`Setting up scrapy-zyte-api <setup>` prevents that through
:setting:`HTTPCACHE_POLICY <scrapy:HTTPCACHE_POLICY>`:

.. autoclass:: scrapy_zyte_api.ScrapyZyteAPIHttpCachePolicy

It extends :class:`~scrapy.extensions.httpcache.DummyPolicy`, the default
policy. The :ref:`add-on <config-addon>` only sets it if you have not set
:setting:`HTTPCACHE_POLICY <scrapy:HTTPCACHE_POLICY>` yourself.
