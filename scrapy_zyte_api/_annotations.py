from enum import Enum


class ExtractFrom(str, Enum):
    """:ref:`Annotation <annotations>` to specify the :ref:`extraction source
    <zyte-api-extract-from>` of an automatic extraction :ref:`input <inputs>`,
    such as :class:`~zyte_common_items.Product` or
    :class:`~zyte_common_items.Article`.

    See :ref:`annotations`.
    """

    httpResponseBody: str = "httpResponseBody"
    browserHtml: str = "browserHtml"
