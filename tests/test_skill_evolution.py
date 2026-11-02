import json
import runpy
from types import SimpleNamespace

import httpx
import pytest

from analyst.config import CORE_ROOT
from analyst.evolution import Evolution, fingerprint
from analyst.skill_evolution import (
    check_skill,
    decision,
    evaluation_identity,
    native_instruction_hash,
    propose_skill,
    skill_path,
    validate_skill,
)
from analyst.skill_release import enable, rollback, stage


def manifest(name="oil_forecast", body="Use forecast for new calculations."):
    return (
        f"---\nname: {name}\ndescription: Calculate forecasts.\nversion: 0.5.0\n"
        f"type: instruction\nos: any\n---\n\n{body}\n"
    )


def candidate(backend, name="oil_forecast", content=None, key="skill-test"):
    return propose_skill(
        backend,
        backend.baseline()["base_sha"],
        name,
        "forecast",
        content or manifest(name),
        "Correct tool routing",
        "trace-fixture",
        key,
    )


def test_skill_candidate_is_versioned_and_never_changes_active_bytes(tmp_path):
    backend = Evolution(tmp_path)
    base = backend.baseline()["base_sha"]
    old = (backend.repo / skill_path("oil_forecast")).read_text()
    state = candidate(backend)
    assert backend.baseline()["base_sha"] == base
    assert (backend.repo / state["artifact"]).read_text() == old
    assert state == candidate(backend)
    assert "forecast" in backend.diff(state["candidate_id"])["diff"]
    with pytest.raises(ValueError, match="conflicts"):
        candidate(backend, content=manifest(body="Different instructions."))
    with pytest.raises(ValueError, match="Checks"):
        backend.review(state["candidate_id"])


@pytest.mark.parametrize("name", ["../core", "x/y", "x\\y", "", "../evals/gold"])
def test_skill_name_cannot_escape_instructions(name):
    with pytest.raises(ValueError):
        skill_path(name)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("type: instruction", "type: extension"),
        lambda s: s.replace("os: any", "permissions: [shell]"),
        lambda s: s.replace("name: oil_forecast", "name: other"),
        lambda s: s.replace("os: any", "always_in_context: true"),
        lambda s: s.replace("os: any", "dependencies: [unsafe]"),
    ],
)
def test_instruction_candidate_cannot_expand_execution_surface(change):
    with pytest.raises(ValueError):
        validate_skill(skill_path("oil_forecast"), change(manifest()))


def test_paired_skill_checks_reject_a_regression_even_with_net_gain(tmp_path, monkeypatch):
    backend = Evolution(tmp_path)
    state = candidate(backend)
    cases = [{"id": str(i), "capability": "forecast", "question": str(i)} for i in range(3)]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    monkeypatch.setenv("SKILL_EVAL_PATH", str(path))

    def decide(instructions, case, tools):
        new = instructions == manifest()
        return {"passed": (case["id"] != "0") if new else case["id"] == "0", "usage": {}}

    result = check_skill(backend, state, decide)
    assert (result["before"], result["after"]) == (1, 2)
    assert not result["passed"] and result["regressions"] == ["0"]


def test_new_skill_requires_all_declared_capability_cases(tmp_path):
    backend = Evolution(tmp_path)
    state = candidate(backend, "seasonal_forecast")
    assert "seasonal_forecast" not in backend.baseline()["skills"]
    result = check_skill(backend, state, lambda *args: {"passed": True, "usage": {}})
    assert result["passed"] and result["new_capability"] and result["after"] == result["total"]
    result = check_skill(backend, state, lambda *args: {"passed": False, "usage": {}})
    assert not result["passed"]


def test_evaluator_checks_tool_arguments_without_executing_tools(monkeypatch):
    import analyst.skill_evolution as module

    calls = []
    message = SimpleNamespace(
        content="",
        usage_metadata={"input_tokens": 15},
        tool_calls=[{"name": "forecast", "args": {"horizon_months": 4}}],
    )

    class Model:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            calls.append(messages)
            return message

    monkeypatch.setattr(module, "chat_model", Model)
    tools = [
        {
            "function": {
                "name": "forecast",
                "parameters": {
                    "type": "object",
                    "properties": {"horizon_months": {"type": "integer", "maximum": 6}},
                    "required": ["horizon_months"],
                },
            }
        }
    ]
    case = {"question": "four months", "tools": ["forecast"], "arguments": {"horizon_months": 4}}
    assert decision("instructions", case, tools)["passed"]
    message.tool_calls[0]["args"]["horizon_months"] = 3
    assert not decision("instructions", case, tools)["passed"]
    message.tool_calls[0]["args"]["horizon_months"] = 99
    assert not decision("instructions", case, tools)["passed"]
    assert len(calls) == 3


def approved(backend, state):
    state["quality_checks"] = {
        "passed": True,
        "identity": evaluation_identity(),
        "candidate_sha": state["candidate_sha"],
    }
    state["critic"] = {
        "verdict": "APPROVE",
        "candidate_sha": state["candidate_sha"],
        "checks_sha256": fingerprint(state["quality_checks"]),
    }
    backend.save(state)


def test_stage_native_hash_review_enable_and_targeted_rollback(tmp_path):
    backend = Evolution(tmp_path)
    state = candidate(backend)
    approved(backend, state)
    review_clean = False
    enabled = True

    def handle(request):
        nonlocal enabled
        content = (backend.repo / state["artifact"]).read_text()
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "skills": [
                        {
                            "name": "oil_forecast",
                            "enabled": enabled,
                            "content_hash": native_instruction_hash(content),
                            "executable_review": review_clean,
                        }
                    ]
                },
            )
        enabled = json.loads(request.content)["enabled"]
        return httpx.Response(200, json={"enabled": enabled})

    with httpx.Client(base_url="http://local", transport=httpx.MockTransport(handle)) as client:
        staged = stage(backend, client, state["candidate_id"], state["candidate_sha"], "operator")
        assert not enabled and staged["status"] == "STAGED_FOR_NATIVE_REVIEW"
        with pytest.raises(ValueError, match="native exact-byte"):
            enable(backend, client, state["candidate_id"], state["candidate_sha"], "operator")
        review_clean = True
        assert (
            enable(backend, client, state["candidate_id"], state["candidate_sha"], "operator")[
                "status"
            ]
            == "SKILL_ENABLED"
        )
        assert enabled
        other = backend.repo / "unrelated.txt"
        other.write_text("keep this later commit")
        backend.git("add", "unrelated.txt")
        backend.git("commit", "-m", "Unrelated change")
        undone = rollback(backend, client, state["candidate_id"], "operator")
        assert not enabled and undone["status"] == "SKILL_ROLLED_BACK"
        assert other.read_text() == "keep this later commit"


def test_launcher_allows_native_readonly_delegation_but_no_child_evolution():
    allowed = runpy.run_path(str(CORE_ROOT / "scripts/native_ouroboros.py"))["tool_allowed"]
    assert allowed("schedule_subagent", {"subagent_id": "forecast-analyst"})
    assert not allowed(
        "schedule_subagent", {"subagent_id": "forecast-analyst", "write_surface": "genesis"}
    )
    assert not allowed("schedule_subagent", {"subagent_id": "forecast-analyst"}, child=True)
    assert allowed("mcp_analyst__forecast", {}, child=True)
    assert not allowed("mcp_evolution__propose_skill", {}, child=True)
    assert allowed("read_file", {"root": "skill_payload", "path": "SKILL.md"})
    assert not allowed("read_file", {"root": "runtime_data", "path": "settings.json"})
    assert not allowed("run_command", {"command": "arbitrary"})


def test_stage_rejects_approval_for_other_bytes_or_stale_evaluation(tmp_path):
    backend = Evolution(tmp_path)
    state = candidate(backend)
    approved(backend, state)
    state["critic"]["candidate_sha"] = "0" * 40
    backend.save(state)
    with httpx.Client(base_url="http://unused") as client:
        with pytest.raises(ValueError, match="APPROVE"):
            stage(backend, client, state["candidate_id"], state["candidate_sha"], "operator")
    assert backend.git("rev-parse", "main") == state["base_sha"]


def test_skill_check_cache_does_not_repeat_paid_calls(tmp_path, monkeypatch):
    import analyst.skill_evolution as module

    backend = Evolution(tmp_path)
    state = candidate(backend)
    calls = []

    def evaluate(*args):
        calls.append(True)
        return {
            "passed": False,
            "candidate_sha": state["candidate_sha"],
            "identity": evaluation_identity(),
        }

    monkeypatch.setattr(module, "check_skill", evaluate)
    backend.checks(state["candidate_id"], real=True)
    backend.checks(state["candidate_id"], real=False)
    assert len(calls) == 1


def test_typed_skill_api_builds_frontmatter_without_model_yaml():
    from analyst.skill_evolution import instruction_manifest

    text = instruction_manifest(
        "brent_forecast",
        "Brent --- forecast: monthly",
        "0.1.0",
        'Use forecast(asset="brent").\nKeep source and intervals.',
    )
    parsed = validate_skill(skill_path("brent_forecast"), text)
    assert parsed["description"] == "Brent --- forecast: monthly"
    assert parsed["version"] == "0.1.0" and parsed["type"] == "instruction"
    assert not parsed["always_in_context"]
    with pytest.raises(ValueError, match="version"):
        instruction_manifest("brent_forecast", "forecast", "1", "body")
