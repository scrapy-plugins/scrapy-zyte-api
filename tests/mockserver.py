from __future__ import annotations
import argparse
import json
import socket
import sys
import time
from base64 import b64encode
from contextlib import asynccontextmanager
from importlib import import_module
from subprocess import PIPE, Popen
from typing import Dict, List, Optional
from urllib.parse import urlparse

from pytest_twisted import ensureDeferred
from scrapy import Request
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import deferLater
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET, Site

from scrapy_zyte_api._annotations import _ActionResult, ExtractFrom
from scrapy_zyte_api.responses import _API_RESPONSE

from . import SETTINGS, make_handler


# https://github.com/scrapy/scrapy/blob/02b97f98e74a994ad3e4d74e7ed55207e508a576/tests/mockserver.py#L27C1-L33C19
def getarg(request, name, default=None, type=None):
    if name in request.args:
        value = request.args[name][0]
        if type is not None:
            value = type(value)
        return value
    return default


def get_ephemeral_port():
    s = socket.socket()
    s.bind(("", 0))
    return s.getsockname()[1]


@ensureDeferred
async def produce_request_response(mockserver, meta, settings=None):
    settings = settings if settings is not None else {**SETTINGS}
    async with mockserver.make_handler(settings) as handler:
        req = Request(mockserver.urljoin("/"), meta=meta)
        resp = await handler.download_request(req, None)
        return req, resp


class LeafResource(Resource):
    isLeaf = True

    def deferRequest(self, request, delay, f, *a, **kw):
        def _cancelrequest(_):
            # silence CancelledError
            d.addErrback(lambda _: None)
            d.cancel()

        # Typing issues: https://github.com/twisted/twisted/issues/9909
        d: Deferred = deferLater(reactor, delay, f, *a, **kw)  # type: ignore[arg-type]
        request.notifyFinish().addErrback(_cancelrequest)
        return d


class DefaultResource(Resource):
    request_count = 0

    def getChild(self, path, request):
        if path == b"count":
            return RequestCountResource()
        return self

    def render_GET(self, request):
        referer = request.getHeader(b"Referer")
        if referer:
            request.responseHeaders.setRawHeaders(b"Referer", [referer])
        return b""

    def render_POST(self, request):
        DefaultResource.request_count += 1
        request_data = json.loads(request.content.read())
        request.responseHeaders.setRawHeaders(
            b"Content-Type",
            [b"application/json"],
        )
        request.responseHeaders.setRawHeaders(
            b"request-id",
            [b"abcd1234"],
        )

        response_data: _API_RESPONSE = {}

        if "url" not in request_data:
            request.setResponseCode(400)
            return json.dumps(response_data).encode()
        response_data["url"] = request_data["url"]

        domain = urlparse(request_data["url"]).netloc
        if "bad-key" in domain:
            request.setResponseCode(401)
            response_data = {
                "status": 401,
                "type": "/auth/key-not-found",
                "title": "Authentication Key Not Found",
                "detail": "The authentication key is not valid or can't be matched.",
            }
            return json.dumps(response_data).encode()
        if "forbidden" in domain:
            request.setResponseCode(451)
            response_data = {
                "status": 451,
                "type": "/download/domain-forbidden",
                "title": "Domain Forbidden",
                "detail": "Extraction for the domain is forbidden.",
                "blockedDomain": domain,
            }
            return json.dumps(response_data).encode()
        if "suspended-account" in domain:
            request.setResponseCode(403)
            response_data = {
                "status": 403,
                "type": "/auth/account-suspended",
                "title": "Account Suspended",
                "detail": "Account is suspended, check billing details.",
            }
            return json.dumps(response_data).encode()
        if "temporary-download-error" in request_data["url"]:
            request.setResponseCode(520)
            response_data = {
                "status": 520,
                "type": "/download/temporary-error",
                "title": "...",
                "detail": "...",
            }
            return json.dumps(response_data).encode()

        html = "<html><body>Hello<h1>World!</h1></body></html>"
        if "browserHtml" in request_data:
            if "httpResponseBody" in request_data:
                request.setResponseCode(422)
                return json.dumps(
                    {
                        "type": "/request/unprocessable",
                        "title": "Unprocessable Request",
                        "status": 422,
                        "detail": "Incompatible parameters were found in the request.",
                    }
                ).encode()
            response_data["browserHtml"] = html
        if "screenshot" in request_data:
            response_data["screenshot"] = b64encode(
                b"screenshot-body-contents"
            ).decode()

        if "session" in request_data:
            # See test_sessions.py::test_param_precedence
            if domain.startswith("postal-code-10001"):
                postal_code = None
                for action in request_data.get("actions", []):
                    try:
                        postal_code = action["address"]["postalCode"]
                    except (KeyError, IndexError, TypeError):
                        pass
                    else:
                        break
                if postal_code != "10001" and not domain.startswith(
                    "postal-code-10001-soft"
                ):
                    request.setResponseCode(500)
                    return b""
            response_data["session"] = request_data["session"]

        if "httpResponseBody" in request_data:
            headers = request_data.get("customHttpRequestHeaders", [])
            for header in headers:
                if header["name"].strip().lower() == "accept":
                    accept = header["value"]
                    break
            else:
                accept = None
            if accept == "application/octet-stream":
                body = b64encode(b"\x00").decode()
            else:
                body = b64encode(html.encode()).decode()
            response_data["httpResponseBody"] = body

        if request_data.get("httpResponseHeaders") is True:
            response_data["httpResponseHeaders"] = [
                {"name": "test_header", "value": "test_value"}
            ]
            headers = request_data.get("customHttpRequestHeaders", [])
            for header in headers:
                if header["name"].strip().lower() == "referer":
                    referer = header["value"]
                    break
            else:
                headers = request_data.get("requestHeaders", {})
                if "referer" in headers:
                    referer = headers["referer"]
                else:
                    referer = None
            if referer is not None:
                assert isinstance(response_data["httpResponseHeaders"], list)
                response_data["httpResponseHeaders"].append(
                    {"name": "Referer", "value": referer}
                )

        actions = request_data.get("actions")
        if actions:
            results: List[_ActionResult] = []
            for action in actions:
                result: _ActionResult = {
                    "action": action["action"],
                    "elapsedTime": 1.0,
                    "status": "success",
                }
                if action["action"] == "setLocation":
                    if domain.startswith("postal-code-10001"):
                        try:
                            postal_code = action["address"]["postalCode"]
                        except (KeyError, IndexError, TypeError):
                            postal_code = None
                        if postal_code != "10001":
                            result["status"] = "returned"
                            result["error"] = "Action setLocation failed"
                    elif domain.startswith("no-location-support"):
                        result["status"] = "returned"
                        result["error"] = "Action setLocation not supported on …"
                results.append(result)
            response_data["actions"] = results  # type: ignore[assignment]

        if request_data.get("product") is True:
            response_data["product"] = {
                "url": response_data["url"],
                "name": "Product name",
                "price": "10",
                "currency": "USD",
            }
            assert isinstance(response_data["product"], dict)
            assert isinstance(response_data["product"]["name"], str)
            extract_from = request_data.get("productOptions", {}).get("extractFrom")
            if extract_from:
                if extract_from == ExtractFrom.httpResponseBody:
                    response_data["product"]["name"] += " (from httpResponseBody)"

            if "geolocation" in request_data:
                response_data["product"]["name"] += (
                    f" (country {request_data['geolocation']})"
                )

            if "customAttributes" in request_data:
                response_data["customAttributes"] = {
                    "metadata": {
                        "textInputTokens": 1000,
                    },
                    "values": {
                        "attr1": "foo",
                        "attr2": 42,
                    },
                }

            if request_data.get("productNavigation") is True:
                response_data["productNavigation"] = {
                    "url": response_data["url"],
                    "name": "Product navigation",
                    "pageNumber": 0,
                }

        return json.dumps(response_data).encode()


class RequestCountResource(LeafResource):
    def render_GET(self, request):
        return str(DefaultResource.request_count).encode()


class DelayedResource(LeafResource):
    def render_POST(self, request):
        data = json.loads(request.content.read())
        seconds = data.get("delay", 0)
        self.deferRequest(
            request,
            seconds,
            self._delayedRender,
            request,
            seconds,
        )
        return NOT_DONE_YET

    def _delayedRender(self, request, seconds):
        request.responseHeaders.setRawHeaders(
            b"Content-Type",
            [b"application/json"],
        )
        request.write(b'{"url": "https://example.com", "browserHtml": "<html></html>"}')
        request.finish()


class MockServer:
    def __init__(self, resource=None, port=None):
        resource = resource or DefaultResource
        self.resource = "{}.{}".format(resource.__module__, resource.__name__)
        self.proc = None
        self.host = socket.gethostbyname(socket.gethostname())
        self.port = port or get_ephemeral_port()
        self.root_url = "http://%s:%d" % (self.host, self.port)

    def __enter__(self):
        self.proc = Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "tests.mockserver",
                self.resource,
                "--port",
                str(self.port),
            ],
            stdout=PIPE,
        )
        assert self.proc.stdout is not None
        self.proc.stdout.readline()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        assert self.proc is not None
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)

    def urljoin(self, path):
        return self.root_url + path

    @asynccontextmanager
    async def make_handler(self, settings: Optional[Dict] = None):
        settings = settings or {}
        async with make_handler(settings, self.urljoin("/")) as handler:
            yield handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("resource")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    module_name, name = args.resource.rsplit(".", 1)
    sys.path.append(".")
    resource = getattr(import_module(module_name), name)()
    # Typing issue: https://github.com/twisted/twisted/issues/9909
    http_port = reactor.listenTCP(args.port, Site(resource))  # type: ignore[attr-defined]

    def print_listening():
        host = http_port.getHost()
        print(
            "Mock server {} running at http://{}:{}".format(
                resource, host.host, host.port
            )
        )

    # Typing issue: https://github.com/twisted/twisted/issues/9909
    reactor.callWhenRunning(print_listening)  # type: ignore[attr-defined]
    reactor.run()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
