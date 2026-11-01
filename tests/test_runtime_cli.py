import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from analyst.config import CORE_ROOT


@pytest.fixture
def cli(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "runtime_cli", CORE_ROOT / "scripts/ouroboros_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "runtime_paths", lambda: (tmp_path, Path("/test/python")))
    return module


def skill(name="oilgas_analyst", reviewed=True):
    return {"name": name, "enabled": True, "executable_review": reviewed, "content_hash": "hash"}


def test_unreviewed_skill_cannot_submit_a_task(cli):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"skills": [skill(reviewed=False)]})

    with httpx.Client(base_url="http://runtime", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="reviewed"):
            cli.submit_task(client, "unused-prompt.txt")
    assert calls == ["/api/extensions"]


def test_submission_disables_extensions_and_withholds_mutating_tools(cli, tmp_path, monkeypatch):
    calls = []
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Create a policy candidate")
    monkeypatch.setattr(
        cli.subprocess,
        "check_output",
        lambda *a, **kw: json.dumps(["finish_task", "enable_tools", "run_command", "write_file"]),
    )

    def handler(request):
        calls.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json={"skills": [skill(), skill("computer_use")]})
        body = json.loads(request.content)
        if request.url.path.endswith("/toggle"):
            assert body == {"enabled": False, "expected_content_hash": "hash"}
            return httpx.Response(200, json={"enabled": False})
        assert body["disabled_tools"] == ["run_command", "write_file"]
        assert body["description"] == prompt.read_text()
        return httpx.Response(200, json={"task_id": "test-task"})

    with httpx.Client(base_url="http://runtime", transport=httpx.MockTransport(handler)) as client:
        assert cli.submit_task(client, prompt).json()["task_id"] == "test-task"
    assert calls == ["/api/extensions", "/api/skills/computer_use/toggle", "/api/tasks"]


def test_submission_stops_if_an_extension_cannot_be_disabled(cli):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"skills": [skill(), skill("computer_use")]})
        assert request.url.path == "/api/skills/computer_use/toggle"
        return httpx.Response(200, json={"enabled": True})

    with httpx.Client(base_url="http://runtime", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="disable"):
            cli.submit_task(client, "unused-prompt.txt")
