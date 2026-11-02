"""Private execution broker. No caller-controlled images, commands or mounts."""

import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from process_executor import execute_many

TOKEN = os.environ["RUNNER_TOKEN"]
IMAGE = os.environ["RUNNER_IMAGE"]
SLOTS = threading.BoundedSemaphore(1)
PENDING = threading.BoundedSemaphore(5)
if len(TOKEN) < 24:
    raise ValueError("Private RUNNER_TOKEN required")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != "/health" or not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + TOKEN
        ):
            self.send_error(401)
            return
        raw = json.dumps({"image": IMAGE, "abi": 2, "confinement": "chroot+uid+seccomp"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + TOKEN):
            self.send_error(401)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if self.path != "/execute" or not 0 < size <= 5 * 1048576:
            self.send_error(400)
            return
        if not PENDING.acquire(blocking=False):
            self.send_error(429)
            return
        acquired = False
        try:
            started = time.monotonic()
            body = json.loads(self.rfile.read(size))
            timeout = float(body.get("timeout", 120))
            if not 0.1 <= timeout <= 120:
                raise ValueError("Invalid job timeout")
            acquired = SLOTS.acquire(timeout=min(10, timeout))
            if not acquired:
                raise TimeoutError("Executor queue wait limit exceeded")
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Execution deadline exceeded in queue")
            result = execute_many(body["source"], body["inputs"], image=IMAGE, timeout=remaining)
            payload = {"results": result, "image": IMAGE}
            code = 200
        except Exception as exc:
            code, payload = (
                422,
                {
                    "error": type(exc).__name__,
                    "detail": str(exc)[-1000:]
                    if isinstance(exc, (ValueError, TimeoutError))
                    else "Execution failed",
                },
            )
        finally:
            if acquired:
                SLOTS.release()
            PENDING.release()
        raw = json.dumps(payload, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


ThreadingHTTPServer(("0.0.0.0", 8013), Handler).serve_forever()
