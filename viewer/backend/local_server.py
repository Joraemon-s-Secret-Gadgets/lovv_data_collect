import mimetypes
import os
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app import lambda_handler


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8787"))


class ViewerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        self._handle_static(parsed.path)

    def do_OPTIONS(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed, method="OPTIONS")
            return
        self.send_response(204)
        self.end_headers()

    def _handle_api(self, parsed, method="GET"):
        query = {
            key: values[-1]
            for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        }
        event = {
            "version": "2.0",
            "rawPath": parsed.path,
            "queryStringParameters": query,
            "headers": {key.lower(): value for key, value in self.headers.items()},
            "requestContext": {"http": {"method": method, "path": parsed.path}},
        }
        response = lambda_handler(event, None)
        self.send_response(response["statusCode"])
        for key, value in response.get("headers", {}).items():
            self.send_header(key, value)
        self.end_headers()
        body = response.get("body", "")
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.wfile.write(body)

    def _handle_static(self, request_path):
        path = posixpath.normpath(request_path.lstrip("/"))
        if path in ("", "."):
            path = "index.html"
        target = (FRONTEND_DIR / path).resolve()
        if not str(target).startswith(str(FRONTEND_DIR.resolve())):
            self.send_error(404)
            return
        if not target.exists() or not target.is_file():
            target = FRONTEND_DIR / "index.html"
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), ViewerHandler)
    print(f"TourKoreaDomainData viewer running at http://{HOST}:{PORT}")
    print("Use MOCK_DATA_PATH=backend/mock-data/sample-items.json for local mock data.")
    server.serve_forever()
