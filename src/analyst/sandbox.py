"""Bounded Docker executor. This module must run in the trusted executor service."""

import json
import os
import selectors
import subprocess
import time
from uuid import uuid4

MAX_OUTPUT = 1048576


def execute(source, payload, *, image, timeout=30):
    if not image.startswith("sha256:") or len(image) != 71:
        raise ValueError("Executor requires a pinned local image digest")
    if not isinstance(source, str) or len(source.encode()) > 64000:
        raise ValueError("Candidate source exceeds 64000 bytes")
    body = json.dumps({"source": source, "input": payload}, allow_nan=False).encode() + b"\n"
    if len(body) > 4 * 1048576:
        raise ValueError("Sandbox input exceeds 4 MiB")
    name = "oilagent-job-" + uuid4().hex
    args = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--memory=1g",
        "--memory-swap=1g",
        "--cpus=1",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
        "--log-driver=none",
        image,
    ]
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.environ["PATH"]},
    )
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    pending = memoryview(body)
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
                        count = os.write(key.fd, pending[:65536])
                        pending = pending[count:]
                    except BrokenPipeError:
                        pending = pending[:0]
                    if not pending:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output[key.data].extend(chunk)
                        if sum(map(len, output.values())) > MAX_OUTPUT:
                            raise ValueError("Sandbox output limit exceeded")
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
        if process.returncode:
            raise ValueError("Candidate failed in sandbox; exit code " + str(process.returncode))
        return json.loads(output["stdout"])
    finally:
        selector.close()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        for stream in [process.stdin, process.stdout, process.stderr]:
            if not stream.closed:
                stream.close()
