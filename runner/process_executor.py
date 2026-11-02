"""Per-job Linux confinement inside a service with no host mounts or Docker access."""

import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from itertools import count

UIDS = count(10000)
UID_LOCK = threading.Lock()

MAX_OUTPUT = 1048576


def execute(source, payload, *, image, timeout=30):
    return execute_many(source, [payload], image=image, timeout=timeout)[0]


def execute_many(source, inputs, *, image, timeout=120):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Executor requires a pinned local image digest")
    if not isinstance(source, str) or not 1 <= len(source.encode()) <= 64000:
        raise ValueError("Candidate source exceeds 64000 bytes")
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 64:
        raise ValueError("Sandbox requires 1..64 sequential inputs")
    messages = [json.dumps(x, allow_nan=False).encode() + b"\n" for x in inputs]
    header = json.dumps({"source": source}).encode() + b"\n"
    if len(header) + sum(map(len, messages)) > 4 * 1048576:
        raise ValueError("Sandbox input exceeds 4 MiB")
    with UID_LOCK:
        uid = next(UIDS)
    if uid > 60000:
        raise RuntimeError("Restart executor to renew job UID space")
    workdir = tempfile.mkdtemp(prefix="job-", dir="/jail/tmp")
    os.chmod(workdir, 0o700)
    os.chown(workdir, uid, uid)
    try:
        return _execute(source, messages, header, image, timeout, workdir, uid)
    finally:
        shutil.rmtree(workdir)


def _execute(source, messages, header, image, timeout, workdir, uid):
    process = subprocess.Popen(
        [sys.executable, "-I", "/worker/launch.py", os.path.basename(workdir), str(uid)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "NUMEXPR_MAX_THREADS": "1",
        },
    )
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    pending = memoryview(header + messages[0])
    results, line, errors, output_bytes = [], bytearray(), bytearray(), 0
    try:
        for stream, kind in [
            (process.stdin, "input"),
            (process.stdout, "stdout"),
            (process.stderr, "stderr"),
        ]:
            os.set_blocking(stream.fileno(), False)
            selector.register(
                stream, selectors.EVENT_WRITE if kind == "input" else selectors.EVENT_READ, kind
            )
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise TimeoutError("Sandbox wall-time limit exceeded")
            for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                if key.data == "input":
                    try:
                        pending = pending[os.write(key.fd, pending[:65536]) :]
                    except BrokenPipeError:
                        pending = pending[:0]
                    if not pending:
                        selector.unregister(key.fileobj)
                else:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output_bytes += len(chunk)
                    if output_bytes > MAX_OUTPUT:
                        raise ValueError("Sandbox output limit exceeded")
                    if key.data == "stderr":
                        errors.extend(chunk)
                    if key.data == "stdout":
                        line.extend(chunk)
                        while b"\n" in line:
                            raw, _, rest = line.partition(b"\n")
                            line = bytearray(rest)
                            results.append(json.loads(raw))
                            if len(results) > len(messages):
                                raise ValueError("Unexpected sandbox output")
                            if len(results) == len(messages):
                                process.stdin.close()
                            else:
                                # Future training prefixes are not queued in the child's pipe.
                                pending = memoryview(messages[len(results)])
                                selector.register(process.stdin, selectors.EVENT_WRITE, "input")
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
        if process.returncode or len(results) != len(messages):
            raise ValueError(
                "Candidate failed in sandbox: " + errors[-1000:].decode(errors="replace")
            )
        return results
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        # Kill all descendants, including children that outlive the main worker.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for stream in [process.stdin, process.stdout, process.stderr]:
            if not stream.closed:
                stream.close()
