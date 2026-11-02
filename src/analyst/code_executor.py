"""Authenticated broker client. Author and analytical services never receive Docker access."""

import os
import time
from contextvars import ContextVar

import httpx

execution_budget = ContextVar("execution_budget", default=None)


class ExecutionError(ValueError):
    """Bounded untrusted worker diagnostics, never a host exception or credential."""

    def __init__(self, detail):
        self.detail = detail[:1000]
        super().__init__(self.detail)


def run_many(source, inputs):
    token = os.getenv("RUNNER_TOKEN", "")
    url = os.getenv("RUNNER_URL", "")
    if len(token) < 24 or not url:
        raise ValueError("Configure the private execution broker")
    budget = execution_budget.get()
    timeout = 120
    if budget is not None:
        budget["calls"] += 1
        timeout = min(timeout, budget["deadline"] - time.monotonic())
        if budget["calls"] > 64 or timeout < 0.1:
            raise TimeoutError("Protected method evaluation budget exhausted")
    with httpx.Client(trust_env=False, timeout=timeout + 10) as client:
        response = client.post(
            url.rstrip("/") + "/execute",
            headers={"Authorization": "Bearer " + token},
            json={"source": source, "inputs": inputs, "timeout": timeout},
        )
        if response.status_code == 422:
            raise ExecutionError(str(response.json().get("detail", "Isolated method failed")))
        response.raise_for_status()
        body = response.json()
    if not body.get("image", "").startswith("sha256:") or len(body["results"]) != len(inputs):
        raise ValueError("Invalid executor receipt")
    return body["results"], body["image"]


def runner_identity():
    with httpx.Client(trust_env=False, timeout=5) as client:
        response = client.get(
            os.environ["RUNNER_URL"].rstrip("/") + "/health",
            headers={"Authorization": "Bearer " + os.environ["RUNNER_TOKEN"]},
        )
        response.raise_for_status()
        return response.json()
