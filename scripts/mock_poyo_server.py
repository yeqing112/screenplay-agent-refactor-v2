from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count
from urllib.parse import urlparse


TASKS: dict[str, dict] = {}
TASK_COUNTER = count(1)

IMAGE_MODELS = {
    "gpt-image-2",
    "nano-banana-2-new",
    "seedream-5.0-lite",
}


def infer_kind(model_name: str, input_payload: dict) -> str:
    task_mode = str(input_payload.get("task_mode") or "").lower()
    if "video" in task_mode:
        return "video"
    if model_name in IMAGE_MODELS:
        return "image"
    return "video"


class MockPoyoHandler(BaseHTTPRequestHandler):
    server_version = "MockPoYo/0.1"

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/generate/submit":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        model_name = str(payload.get("model") or "")
        input_payload = payload.get("input") or {}
        should_fail = bool(input_payload.get("force_failure"))
        task_id = f"mock-poyo-{next(TASK_COUNTER):04d}"
        kind = infer_kind(model_name, input_payload if isinstance(input_payload, dict) else {})
        TASKS[task_id] = {
            "task_id": task_id,
            "model": model_name,
            "kind": kind,
            "input": input_payload,
            "status": "failed" if should_fail else "finished",
        }
        self._send_json(200, {"task_id": task_id, "status": "submitted"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/generate/status/"):
            self._send_json(404, {"error": "not found"})
            return

        task_id = parsed.path.rsplit("/", 1)[-1]
        task = TASKS.get(task_id)
        if not task:
            self._send_json(404, {"error": "task not found"})
            return

        if task["status"] == "failed":
            self._send_json(
                200,
                {
                    "task_id": task_id,
                    "status": "failed",
                    "error": "mock poyo requested failure",
                    "input": task["input"],
                },
            )
            return

        extension = "png" if task["kind"] == "image" else "mp4"
        self._send_json(
            200,
            {
                "task_id": task_id,
                "status": "finished",
                "model": task["model"],
                "files": [
                    {
                        "file_url": f"https://mock-poyo.local/{task_id}.{extension}",
                    }
                ],
                "input": task["input"],
            },
        )


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 19090
    server = ThreadingHTTPServer(("127.0.0.1", port), MockPoyoHandler)
    print(f"Mock PoYo server listening on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
