.. _redirect:

=========
Redirects
=========

When you send a request through Zyte API, :ref:`by default
<zapi-http-redirection>` any redirects are handled internally by Zyte API.
Scrapy's own redirect middleware
(:class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware`) does not
see these redirects, and therefore does not log them.

scrapy-zyte-api detects when the URL of a Zyte API response differs from the
URL of the originating request, and logs a debug message in that case::

    Redirecting to <200 https://final-url.example> from <GET https://original-url.example>

.. note::

    Unlike Scrapy's redirect log messages, which are emitted for each
    individual redirect, this message only reflects the change from the initial
    request URL to the final response URL. The actual chain of URL changes that
    happened in between may include multiple HTTP redirects,
    JavaScript-triggered URL changes without actual HTTP redirects, or other
    scenarios.
