.. _stats:

=====
Stats
=====

Stats from :doc:`python-zyte-api <python-zyte-api:index>` are exposed as
:ref:`Scrapy stats <topics-stats>` with the ``scrapy-zyte-api`` prefix.

For example, ``scrapy-zyte-api/status_codes/<status code>`` stats indicate the
status code of Zyte API responses (e.g. ``429`` for :ref:`rate limiting
<zyte-api-rate-limit>` or ``520`` for :ref:`temporary download errors
<zyte-api-temporary-download-errors>`).

.. note:: The actual status code that is received from the target website, i.e.
    the :http:`response:statusCode` response field of a :ref:`Zyte API
    successful response <zyte-api-successful-responses>`, is accounted for in
    the ``downloader/response_status_count/<status code>`` stat, as with any
    other Scrapy response.
