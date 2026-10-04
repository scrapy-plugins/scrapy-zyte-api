.. _session-api:

========
Sessions
========

API for :ref:`plugin-managed sessions <session>`. See also the
:class:`~scrapy_zyte_api.Session` :ref:`page input <inputs>`.

Session configs
===============

.. autoclass:: scrapy_zyte_api.SessionConfig
    :members:

.. autofunction:: scrapy_zyte_api.session_config

.. autoclass:: scrapy_zyte_api.LocationSessionConfig
    :members: location_check, location_params

.. autodata:: scrapy_zyte_api.session_config_registry
    :annotation:


Components
==========

.. autoclass:: scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware
    :members:

.. autoclass:: scrapy_zyte_api.ScrapyZyteAPISessionResetterDownloaderMiddleware


Functions
=========

.. autofunction:: scrapy_zyte_api.is_session_init_request

.. autofunction:: scrapy_zyte_api.get_request_session_id


Exceptions
==========

.. autoexception:: scrapy_zyte_api.NoSession


Retry policies
==============

.. autodata:: scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY
    :annotation:

.. autodata:: scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY
    :annotation:
