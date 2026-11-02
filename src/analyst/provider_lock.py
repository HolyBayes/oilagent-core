"""Serialize GigaChat calls across local processes sharing one account."""

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def provider_slot():
    path = Path(
        os.getenv(
            "LLM_LOCK_PATH",
            str(Path(__file__).resolve().parents[2] / "workspace/llm/gigachat.lock"),
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + float(os.getenv("REQUEST_TIMEOUT_SEC", "120"))
    with open(path, "a", opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                from analyst.budget import BudgetExceeded, current_budget

                budget = current_budget.get()
                if budget:
                    budget.check()
                if time.monotonic() >= deadline:
                    raise BudgetExceeded("provider_slot_wait")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
