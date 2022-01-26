import json
from base64 import b64encode
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import urljoin


class MockServer:
    def __enter__(self):
        self.httpd = HTTPServer(("127.0.0.1", 0), _RequestHandler)
        self.address, self.port = self.httpd.server_address
        self.thread = Thread(target=self.httpd.serve_forever)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.httpd.shutdown()
        self.thread.join()

    def urljoin(self, url: str) -> str:
        return urljoin("http://{}:{}".format(self.address, self.port), url)


class _RequestHandler(BaseHTTPRequestHandler):
    def _send_response(self, status: int, content: str, content_type: str):
        self.send_response(status)
        self.send_header("Content-type", content_type)
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def do_POST(self):  # NOQA
        content_length = int(self.headers["Content-Length"])
        try:
            post_data = json.loads(self.rfile.read(content_length).decode("utf-8"))
            url = post_data["url"]
        except (AttributeError, TypeError, ValueError, KeyError) as er:
            self._send_response(400, str(er), "text/html")
            return
        if self.path == "/exception/extract":
            self._send_response(400, "", "text/html")
        else:
            base_response = {"url": url}
            if post_data.get("httpResponseHeaders"):
                base_response["httpResponseHeaders"] = [
                    {"name": "test_header", "value": "test_value"}
                ]
            if post_data.get("jobId") is None:
                browser_html = "<html></html>"
            else:
                browser_html = f"<html>{post_data['jobId']}</html>"
            if post_data.get("browserHtml"):
                base_response["browserHtml"] = browser_html
                self._send_response(200, json.dumps(base_response), "application/json")
            else:
                base_response["httpResponseBody"] = b64encode(
                    browser_html.encode("utf-8")
                ).decode("utf-8")
                self._send_response(200, json.dumps(base_response), "application/json")
