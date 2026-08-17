import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": "nomic-embed-text"}]})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/embed":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            values = payload.get("input") or []
            embeddings = [[0.01, 0.02, 0.03, 0.04] for _ in values]
            self._send(200, {"embeddings": embeddings})
            return
        self._send(404, {"error": "not found"})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 11434), Handler)
    server.serve_forever()
