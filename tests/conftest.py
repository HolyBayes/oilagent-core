"""Unit tests execute only byte-identical developer seeds; candidates require Docker."""

import hashlib

import pytest

from analyst.code_packages import SLOTS, seed_source


@pytest.fixture(autouse=True)
def trusted_seed_executor(monkeypatch):
    import analyst.code_executor as executor

    trusted = {hashlib.sha256(seed_source(slot).encode()).hexdigest() for slot in SLOTS}

    def run(source, inputs):
        if hashlib.sha256(source.encode()).hexdigest() not in trusted:
            raise ValueError("Untrusted Python must run in Docker, including during tests")
        scope = {}
        exec(compile(source, "trusted-developer-seed", "exec"), scope)
        return [scope["run"](request) for request in inputs], "sha256:" + "0" * 64

    monkeypatch.setattr(executor, "run_many", run)
