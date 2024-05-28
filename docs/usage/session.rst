.. _session:

==================
Session management
==================

Zyte API provides powerful session APIs:

-   :ref:`Client-managed sessions <zyte-api-session-id>` give you full control
    over session management.

-   :ref:`Server-managed sessions <zyte-api-session-contexts>` let Zyte API
    handle session management for you.

When using scrapy-zyte-api, you can use these session APIs through the
corresponding Zyte API fields (:http:`request:session`,
:http:`request:sessionContext`).

However, scrapy-zyte-api also provides :ref:`its own session API
<plugin-sessions>`.

.. _plugin-sessions:

scrapy-zyte-api’s session API
=============================

scrapy-zyte-api’s session API offers an API similar to that of
:ref:`server-managed sessions <zyte-api-session-contexts>`, but built on top of
:ref:`client-managed sessions <zyte-api-session-id>`, to provide the best of
both.

scrapy-zyte-api can automatically build a pool of sessions, rotate them and
manage their life cycle. You can use the :setting:`ZYTE_API_SESSION_PARAMS`
setting to define the parameters needed to initialize a session, and the
:setting:`ZYTE_API_SESSION_CHECKER` setting to define a session validity check,
so that responses that fail the check have their session discarded and get a
retry request with a different session.

Often it makes sense to define both settings. For example:

.. code-block:: python
    :caption: settings.py

    from scrapy import Request
    from scrapy.http.response import Response

    ZYTE_API_SESSION_PARAMS = {
        "browserHtml": True,
        "actions": [
            {
                "action": "setLocation",
                "address": {"postalCode": "04662"},
            }
        ],
    }


    class MySessionChecker:

        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        def __init__(self, crawler):
            params = crawler.settings["ZYTE_API_SESSION_PARAMS"]
            self.zip_code = params["actions"][0]["address"]["postalCode"]

        def check_session(self, request: Request, response: Response) -> bool:
            return response.css(".zip_code::text").get() == self.zip_code


    ZYTE_API_SESSION_CHECKER = MySessionChecker

Session checking can be useful to work around scenarios where session
initialization fails, e.g. due to rendering issues, IP-geolocation mismatches,
A-B tests, etc. It can also help in cases where website sessions expire before
Zyte API sessions.

scrapy-zyte-api also gives you control over the number of sessions in the pool
(:setting:`ZYTE_API_SESSION_COUNT`) or the number of :ref:`unsuccessful
responses <zyte-api-unsuccessful-responses>` needed to discard a session
(:setting:`ZYTE_API_SESSION_MAX_ERRORS`).
