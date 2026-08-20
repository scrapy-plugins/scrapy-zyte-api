.. _stats:

=====
Stats
=====

scrapy-zyte-api exposes the following :ref:`Scrapy stats <topics-stats>` with
the ``scrapy-zyte-api`` prefix:

.. stat:: scrapy-zyte-api/429

``scrapy-zyte-api/429``
    Number of Zyte API responses with status code 429. See
    :ref:`zapi-rate-limit`.

.. stat:: scrapy-zyte-api/attempts

``scrapy-zyte-api/attempts``
    Total number of Zyte API request attempts, including retries.

.. stat:: scrapy-zyte-api/auto_fields/{cls}

``scrapy-zyte-api/auto_fields/{cls}``
    Space-separated list of auto fields for the page object class ``{cls}``,
    or the string ``(all fields)`` if all fields are auto fields.

    Only set when :setting:`ZYTE_API_AUTO_FIELD_STATS` is ``True``.

.. stat:: scrapy-zyte-api/error_ratio

``scrapy-zyte-api/error_ratio``
    Ratio of :ref:`unsuccessful responses <zapi-unsuccessful-responses>` to
    :stat:`scrapy-zyte-api/processed`.

.. stat:: scrapy-zyte-api/error_types/{error_type}

``scrapy-zyte-api/error_types/{error_type}``
    Number of :ref:`unsuccessful responses <zapi-unsuccessful-responses>` for
    each error type, where ``{error_type}`` is the ``type`` field from the
    Zyte API error response.

.. stat:: scrapy-zyte-api/errors

``scrapy-zyte-api/errors``
    Total number of :ref:`unsuccessful responses <zapi-unsuccessful-responses>`.

.. stat:: scrapy-zyte-api/exception_types/{exception_type}

``scrapy-zyte-api/exception_types/{exception_type}``
    Number of exceptions of type ``{exception_type}`` raised during Zyte API
    request processing.

.. stat:: scrapy-zyte-api/fatal_errors

``scrapy-zyte-api/fatal_errors``
    Number of unrecoverable Zyte API errors, such as requests with invalid
    parameters.

.. stat:: scrapy-zyte-api/mean_connection_seconds

``scrapy-zyte-api/mean_connection_seconds``
    Mean connection time in seconds across all Zyte API requests.

.. stat:: scrapy-zyte-api/mean_response_seconds

``scrapy-zyte-api/mean_response_seconds``
    Mean total time in seconds from sending a Zyte API request to receiving
    the full response.

.. stat:: scrapy-zyte-api/processed

``scrapy-zyte-api/processed``
    Total number of Zyte API request attempts with a definitive outcome
    (either success or error).

.. stat:: scrapy-zyte-api/request_args/{arg}

``scrapy-zyte-api/request_args/{arg}``
    Number of Zyte API requests that used parameter ``{arg}``.

    For ``experimental`` sub-parameters, the stat name uses dot notation:
    ``scrapy-zyte-api/request_args/experimental.{subarg}``.

.. _session-stats:

.. note:: :ref:`Session <session>` stats (``scrapy-zyte-api/sessions/…``) are
    aggregated across all session pools by default. Set
    :setting:`ZYTE_API_SESSION_STATS_PER_POOL` to ``True`` to enable per-pool
    stats. The ``pools/{pool}/`` fragment in the stat names below is only
    present when per-pool stats are enabled.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/init/check-error

``scrapy-zyte-api/sessions/pools/{pool}/init/check-error``
    Number of times that a session for pool ``{pool}`` triggered an unexpected
    exception during its session validation check right after initialization.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.check <scrapy_zyte_api.SessionConfig.check>`; the
    logs should contain an error message with a traceback for such errors.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/init/check-failed

``scrapy-zyte-api/sessions/pools/{pool}/init/check-failed``
    Number of times that a session from pool ``{pool}`` failed its session
    validation check right after initialization.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/init/check-passed

``scrapy-zyte-api/sessions/pools/{pool}/init/check-passed``
    Number of times that a session from pool ``{pool}`` passed its session
    validation check right after initialization.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/init/failed

``scrapy-zyte-api/sessions/pools/{pool}/init/failed``
    Number of times that initializing a session for pool ``{pool}`` resulted
    in an :ref:`unsuccessful response <zapi-unsuccessful-responses>`.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/init/param-error

``scrapy-zyte-api/sessions/pools/{pool}/init/param-error``
    Number of times that initializing a session for pool ``{pool}`` triggered
    an unexpected exception when obtaining the Zyte API parameters for session
    initialization.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.params <scrapy_zyte_api.SessionConfig.params>`; the
    logs should contain an error message with a traceback for such errors.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/use/check-error

``scrapy-zyte-api/sessions/pools/{pool}/use/check-error``
    Number of times that a response that used a session from pool ``{pool}``
    triggered an unexpected exception during its session validation check.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.check <scrapy_zyte_api.SessionConfig.check>`; the
    logs should contain an error message with a traceback for such errors.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/use/check-failed

``scrapy-zyte-api/sessions/pools/{pool}/use/check-failed``
    Number of times that a response that used a session from pool ``{pool}``
    failed its session validation check.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/use/check-passed

``scrapy-zyte-api/sessions/pools/{pool}/use/check-passed``
    Number of times that a response that used a session from pool ``{pool}``
    passed its session validation check.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/use/expired

``scrapy-zyte-api/sessions/pools/{pool}/use/expired``
    Number of times that a session from pool ``{pool}`` expired.

.. stat:: scrapy-zyte-api/sessions/pools/{pool}/use/failed

``scrapy-zyte-api/sessions/pools/{pool}/use/failed``
    Number of times that a request that used a session from pool ``{pool}``
    got an :ref:`unsuccessful response <zapi-unsuccessful-responses>`.

.. stat:: scrapy-zyte-api/sessions/use/disabled

``scrapy-zyte-api/sessions/use/disabled``
    Number of processed requests for which session management was disabled.

.. stat:: scrapy-zyte-api/status_codes/{status_code}

``scrapy-zyte-api/status_codes/{status_code}``
    Number of Zyte API responses with HTTP status code ``{status_code}``, e.g.
    ``429`` for :ref:`rate limiting <zapi-rate-limit>` or ``520`` for
    :ref:`temporary download errors <zapi-temporary-download-errors>`.

    .. note:: The actual status code received from the target website, i.e.
        the :http:`response:statusCode` response field of a :ref:`Zyte API
        successful response <zapi-successful-responses>`, is accounted for in
        the ``downloader/response_status_count/{status_code}`` stat, as with
        any other Scrapy response.

.. stat:: scrapy-zyte-api/success

``scrapy-zyte-api/success``
    Number of :ref:`successful Zyte API responses <zapi-successful-responses>`.

.. stat:: scrapy-zyte-api/success_ratio

``scrapy-zyte-api/success_ratio``
    Ratio of :ref:`successful responses <zapi-successful-responses>` to
    :stat:`scrapy-zyte-api/processed`.

.. stat:: scrapy-zyte-api/throttle_ratio

``scrapy-zyte-api/throttle_ratio``
    Ratio of :ref:`rate-limited responses <zapi-rate-limit>` to
    :stat:`scrapy-zyte-api/processed`.
