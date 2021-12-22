import json
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
            if post_data.get("jobId") is None:
                browser_html = "<html></html>"
            else:
                browser_html = f"<html>{post_data['jobId']}</html>"
            self._send_response(
                200,
                json.dumps({"url": url, "browserHtml": browser_html}),
                "application/json",
            )
