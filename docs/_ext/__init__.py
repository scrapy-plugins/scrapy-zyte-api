import re

from docutils import nodes
from docutils.parsers.rst.roles import set_classes


def http_api_reference_role(
    name, rawtext, text, lineno, inliner, options=None, content=None
):
    if options is None:
        options = {}
    if content is None:
        content = []
    match = re.search(
        r"(?s)^(.+?)\s*<\s*((?:request|response):[a-zA-Z.]+)\s*>\s*$", text
    )
    if match:
        display_text = match[1]
        reference = match[2]
    else:
        display_text = None
        reference = text
    if reference.startswith("request:"):
        request_or_response = "request"
    elif reference.startswith("response:"):
        request_or_response = "response/200"
    else:
        raise ValueError(
            f":http: directive reference must start with request: or "
            f"response:, got {reference} from {text!r}."
        )

    field = reference.split(":", maxsplit=1)[1]
    if not display_text:
        display_text = field
    refuri = (
        f"https://docs.zyte.com/zyte-api/usage/reference.html"
        f"#operation/extract/{request_or_response}/{field}"
    )
    set_classes(options)
    node = nodes.reference(rawtext, display_text, refuri=refuri, **options)
    return [node], []


def setup(app):
    app.add_role("http", http_api_reference_role)
