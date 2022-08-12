import argparse
import json
import socket
import sys
import time
from base64 import b64encode
from contextlib import asynccontextmanager
from importlib import import_module
from subprocess import PIPE, Popen

from pytest_twisted import ensureDeferred
from scrapy import Request
from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET, Site

from . import make_handler


def get_ephemeral_port():
    s = socket.socket()
    s.bind(("", 0))
    return s.getsockname()[1]


@ensureDeferred
async def produce_request_response(mockserver, meta, settings=None):
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

        d = deferLater(reactor, delay, f, *a, **kw)
        request.notifyFinish().addErrback(_cancelrequest)
        return d


class DefaultResource(LeafResource):
    def render_POST(self, request):
        request_data = json.loads(request.content.read())
        request.responseHeaders.setRawHeaders(
            b"Content-Type",
            [b"application/json"],
        )

        response_data = {}
        if "url" not in request_data:
            request.setResponseCode(400)
            return json.dumps(response_data).encode()
        response_data["url"] = request_data["url"]

        if request_data.get("jobId") is not None:
            html = f"<html>{request_data['jobId']}</html>"
        else:
            html = "<html><body>Hello<h1>World!</h1></body></html>"

        if "browserHtml" in request_data:
            if (
                "httpResponseBody" in request_data
                and not request_data.get("passThrough")
            ):
                request.setResponseCode(422)
                return json.dumps({
                    "type": "/request/unprocessable",
                    "title": "Unprocessable Request",
                    "status": 422,
                    "detail": "Incompatible parameters were found in the request."
                }).encode()
            response_data["browserHtml"] = html
        if "httpResponseBody" in request_data:
            base64_html = b64encode(html.encode()).decode()
            response_data["httpResponseBody"] = base64_html

        if "httpResponseHeaders" in request_data:
            response_data["httpResponseHeaders"] = [
                {"name": "test_header", "value": "test_value"}
            ]

        return json.dumps(response_data).encode()


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
        host = socket.gethostbyname(socket.gethostname())
        self.port = port or get_ephemeral_port()
        self.root_url = "http://%s:%d" % (host, self.port)

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
        self.proc.stdout.readline()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)

    def urljoin(self, path):
        return self.root_url + path

    @asynccontextmanager
    async def make_handler(self, settings: dict = None):
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
    http_port = reactor.listenTCP(args.port, Site(resource))

    def print_listening():
        host = http_port.getHost()
        print(
            "Mock server {} running at http://{}:{}".format(
                resource, host.host, host.port
            )
        )

    reactor.callWhenRunning(print_listening)
    reactor.run()


if __name__ == "__main__":
    main()
