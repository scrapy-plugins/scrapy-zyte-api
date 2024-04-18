.. _session:

==================
Session management
==================

Zyte API provides powerful session APIs:

-   Client-managed sessions give you full control over session management.

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

scrapy-zyte-api’s session API offers a higher-level API on top of
client-managed sessions, to enjoy some of the advantages of client-managed
sessions (e.g. expiring specific sessions) while removing some of their
drawbacks (management overhead).

To use scrapy-zyte-api’s session API, define
:setting:`ZYTE_API_SESSION_PARAMS` or :setting:`ZYTE_API_SESSION_CHECKER`.

Often it makes sense to define both. For example:

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

You can also use :setting:`ZYTE_API_SESSION_COUNT` to customize the number of
concurrent sessions to use.
