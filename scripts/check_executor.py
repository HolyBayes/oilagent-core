"""Explicit live checks of the private executor. No model calls or host mounts."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from analyst.code_packages import seed_source
from analyst.config import CORE_ROOT


def main():
    load_dotenv(CORE_ROOT / ".env", override=False)
    url = os.environ["RUNNER_URL"].rstrip("/")
    checks = {}
    with httpx.Client(
        base_url=url,
        headers={"Authorization": "Bearer " + os.environ["RUNNER_TOKEN"]},
        timeout=130,
        trust_env=False,
    ) as client:

        def run(source, inputs, timeout=120):
            return client.post(
                "/execute", json={"source": source, "inputs": inputs, "timeout": timeout}
            )

        response = client.get("/health")
        response.raise_for_status()
        identity = response.json()
        source = """def run(request):
    import errno, os, socket
    out = {"unprivileged": os.getuid() >= 10000, "no_secret": "RUNNER_TOKEN" not in os.environ}
    for name, action in [
        ("network_denied", lambda: socket.socket()),
        ("session_escape_denied", lambda: os.setsid()),
        ("global_scratch_denied", lambda: open("/tmp/global-leak", "w")),
    ]:
        try:
            action()
            out[name] = False
        except PermissionError:
            out[name] = True
    out["private_filesystem"] = all(not os.path.exists(p) for p in [
        "/proc", "/app", "/evolution", "/var/run/docker.sock", "/worker/service.py"
    ])
    with open("allowed.txt", "w") as f:
        f.write("ok")
    out["private_scratch"] = open("allowed.txt").read() == "ok"
    return out
"""
        response = run(source, [{}])
        response.raise_for_status()
        checks.update(response.json()["results"][0])
        response = run(
            seed_source("forecast"),
            [{"values": [60 + (i % 7) + i / 30 for i in range(100)], "horizon": 3}],
        )
        response.raise_for_status()
        checks["numerical_dependencies"] = (
            len(response.json()["results"][0]["points"]["ARIMA"]) == 3
        )
        response = run("def run(request):\n    while True: pass\n", [{}], timeout=0.3)
        checks["timeout"] = (
            response.status_code == 422 and response.json()["error"] == "TimeoutError"
        )
        response = run('def run(request): return "x" * 1100000', [{}])
        checks["output_limit"] = response.status_code == 422
        response = run('def run(request): return request["n"] + 1', [{"n": 1}, {"n": 2}])
        checks["sequential_requests"] = response.json()["results"] == [2, 3]
        response = run("def run(request): return request.query", [{"query": "oil"}])
        checks["bounded_diagnostics"] = (
            response.status_code == 422
            and "AttributeError" in response.json().get("detail", "")
            and len(response.json()["detail"]) <= 1000
        )

        def queued(n):
            response = run(
                "def run(request):\n    import os, time\n    time.sleep(.3)\n"
                '    return {"n": request["n"], "uid": os.getuid()}\n',
                [{"n": n}],
                timeout=10,
            )
            response.raise_for_status()
            return response.json()["results"][0]

        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(queued, range(4)))
        checks["concurrent_queue"] = [row["n"] for row in rows] == list(range(4)) and len(
            {row["uid"] for row in rows}
        ) == 4
    with httpx.Client(base_url=url, trust_env=False) as anonymous:
        checks["authentication"] = anonymous.get("/health").status_code == 401
    evidence = {
        "at": datetime.now(timezone.utc).isoformat(),
        "identity": identity,
        "checks": checks,
    }
    path = CORE_ROOT / "docs/executor-evidence.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    if not all(checks.values()):
        raise SystemExit("Executor confinement checks failed")


if __name__ == "__main__":
    main()
