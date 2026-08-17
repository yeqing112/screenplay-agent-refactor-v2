import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PNG_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X3n0AAAAASUVORK5CYII='

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/v1/models':
            self._send(200, {'data': [{'id': 'fake-image-model'}]})
            return
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path == '/v1/images/generations':
            length = int(self.headers.get('Content-Length', '0'))
            raw = self.rfile.read(length) if length else b'{}'
            payload = json.loads(raw.decode('utf-8'))
            prompt = payload.get('prompt', '')
            self._send(200, {
                'data': [{
                    'b64_json': PNG_BASE64,
                    'revised_prompt': f"{prompt} [fake-provider]" if prompt else 'fake-provider',
                }],
            })
            return
        self._send(404, {'error': 'not found'})

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 8891), Handler)
    server.serve_forever()
