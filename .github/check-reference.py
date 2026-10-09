import json
import os
import re
from urllib.request import Request, urlopen

import yaml

from scrapy_zyte_api._params import _REQUEST_PARAMS

URL = "https://docs.zyte.com/zyte-api/usage/reference.md"

TRACKED = {
    "experimental": 144,
    "extractFrom": 339,
    "includeIframes": 337,
    "pageContent": 338,
    "pageContentOptions": 338,
    "verifyCertificate": 337,
}
"""Fields whose misalignment is tracked in the issue or pull request with the
given number, and therefore not reported until it is closed."""


def is_closed(number):
    request = Request(
        f"https://api.github.com/repos/scrapy-plugins/scrapy-zyte-api/issues/{number}"
    )
    if token := os.environ.get("GH_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    with urlopen(request) as response:  # noqa: S310
        return json.load(response)["state"] == "closed"


def resolve(spec, schema):
    while "$ref" in schema:
        path = schema["$ref"].removeprefix("#/").split("/")
        schema = spec
        for key in path:
            schema = schema[key]
    return schema


def main():
    """Print the differences between the request fields of the Zyte API
    reference and _REQUEST_PARAMS as Markdown, or nothing if there are none."""
    with urlopen(URL) as response:
        text = response.read().decode()
    spec = yaml.safe_load(re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL)[1])
    request = resolve(
        spec,
        spec["paths"]["/extract"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ],
    )
    fields = {
        name: resolve(spec, schema) for name, schema in request["properties"].items()
    }

    misalignments = [
        (name, f"`{name}` is missing from `_REQUEST_PARAMS`.")
        for name in fields
        if name not in _REQUEST_PARAMS
    ]
    misalignments += [
        (name, f"`{name}` is in `_REQUEST_PARAMS` but not in the reference.")
        for name in _REQUEST_PARAMS
        if name not in fields
    ]
    misalignments += [
        (
            name,
            (
                f"`{name}` defaults to `{schema['default']!r}` in the reference "
                f"but to `{_REQUEST_PARAMS[name]['default']!r}` in "
                "`_REQUEST_PARAMS`."
            ),
        )
        for name, schema in fields.items()
        if "default" in schema
        and name in _REQUEST_PARAMS
        and schema["default"] != _REQUEST_PARAMS[name]["default"]
    ]

    lines = []
    for name, line in misalignments:
        if name not in TRACKED:
            lines.append(f"- {line}")
        elif is_closed(TRACKED[name]):
            lines.append(f"- {line} #{TRACKED[name]} is closed.")
    lines += [
        f"- `{name}` is aligned, remove it from `TRACKED`."
        for name in TRACKED.keys() - {name for name, _ in misalignments}
    ]
    if lines:
        print(
            f"The [Zyte API reference]({URL}) request fields and "
            "`scrapy_zyte_api._params._REQUEST_PARAMS` differ:\n"
        )
        print("\n".join(lines))


if __name__ == "__main__":
    main()
