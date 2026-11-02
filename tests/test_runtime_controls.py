import json
import runpy
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

from analyst.budget import Budget, BudgetExceeded
from analyst.provider_lock import provider_slot
from analyst.quality import evaluate
from analyst.traces import record_feedback, save_trace


def test_shared_provider_slot_serializes_and_releases(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_LOCK_PATH", str(tmp_path / "llm.lock"))
    active = 0
    maximum = 0
    lock = threading.Lock()

    def work():
        nonlocal active, maximum
        with provider_slot():
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: work(), range(3)))
    assert maximum == 1
    with pytest.raises(RuntimeError), provider_slot():
        raise RuntimeError("failed provider")
    work()


def test_money_reservation_rejects_unbounded_output_before_call(monkeypatch):
    monkeypatch.setenv("REQUEST_MAX_COST", ".5")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "None")
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_MILLION", "100")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_MILLION", "100")
    budget = Budget()
    with pytest.raises(BudgetExceeded, match="explicit_output_bound"):
        budget.reserve_llm([("human", "test")])
    assert budget.llm_calls == 0


def test_real_check_binds_case_hash_and_rejects_regressions(tmp_path, monkeypatch):
    cases = [
        {
            "case_id": "a",
            "question": "a",
            "expected_publisher": "EIA",
            "expected_page": 1,
            "supporting_text": "support",
            "split": "development",
        },
        {
            "case_id": "b",
            "question": "b",
            "expected_publisher": "EIA",
            "expected_page": 1,
            "supporting_text": "support",
            "split": "holdout",
        },
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    monkeypatch.setenv("EVOLUTION_EVAL_PATH", str(path))
    monkeypatch.setenv("RELEASE_PATH", str(tmp_path / "releases"))

    def search(question, policy):
        candidate = policy.get("reranker") == "bm25"
        if (question == "a") == candidate:
            return [{"publisher": "EIA", "page": 1, "text": "support"}]
        return []

    index = SimpleNamespace(search=search, embedding={"model": "fixture"})
    result = evaluate(
        {"comparison_strategy": "per_publisher", "top_k_per_publisher": 4, "reranker": "bm25"},
        index=index,
    )
    assert not result["passed"] and result["regressions"] == ["b"]
    assert result["splits"]["development"] == {"before": 0, "after": 1, "total": 1}
    assert len(result["eval_sha256"]) == 64


def test_feedback_is_separate_from_evidence_and_trace_redacts(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path))
    secret = "a-configured-secret-value"
    monkeypatch.setenv("LLM_API_KEY", secret)
    request_id = str(uuid4())
    save_trace({"request_id": request_id, "answer": secret})
    assert secret not in (tmp_path / f"{request_id}.json").read_text()
    assert record_feedback(request_id, -1, "Источник не соответствует вопросу")["stored"]
    assert (
        json.loads((tmp_path / f"{request_id}.feedback.json").read_text())["kind"]
        == "unverified_user_feedback"
    )
    with pytest.raises(ValueError):
        record_feedback(str(uuid4()), 1, "unknown trace")


def test_native_adapter_guards_tools_and_delivers_exact_mcp_answer(monkeypatch):
    package = ModuleType("ouroboros")
    agent = ModuleType("ouroboros.agent")
    loop = ModuleType("ouroboros.loop")
    registry_module = ModuleType("ouroboros.tools.registry")
    result_module = ModuleType("ouroboros.tools.tool_result")
    calls = []
    payload = {
        "request_id": str(uuid4()),
        "status": "forecasted",
        "answer": "Исторический ряд [F1]",
    }

    class Registry:
        def __init__(self):
            self._ctx = SimpleNamespace(current_chat_id=42)

        def execute_result(self, name, args):
            calls.append((name, args))
            return SimpleNamespace(status="ok", text=json.dumps(payload))

    def original_loop(*args, **kwargs):
        kwargs["tools"].execute_result("mcp_analyst__answer_question", {"question": "Brent"})
        return "incorrect model paraphrase", {}, {}

    loop.run_llm_loop = original_loop
    agent.run_llm_loop = original_loop
    registry_module.ToolRegistry = Registry
    result_module.ToolResult = lambda **kwargs: SimpleNamespace(**kwargs)
    package.agent, package.loop = agent, loop
    for name, module in {
        "ouroboros": package,
        "ouroboros.agent": agent,
        "ouroboros.loop": loop,
        "ouroboros.tools.registry": registry_module,
        "ouroboros.tools.tool_result": result_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    helper = runpy.run_path(str(Path(__file__).parents[1] / "scripts/native_ouroboros.py"))
    helper["install_delivery_adapter"]()
    registry = Registry()
    assert registry.execute_result("run_shell", {"cmd": "forbidden"}).status == "blocked"
    assert calls == []
    text, usage, trace = agent.run_llm_loop(tools=registry)
    assert payload["answer"] in text and "incorrect" not in text
    assert trace["canonical_analyst_delivery"] == [payload["request_id"]]
    assert calls[0][1]["session_id"].startswith("native-")


def test_unknown_provider_cost_stays_reserved(monkeypatch):
    monkeypatch.setenv("REQUEST_MAX_COST", ".00025")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "100")
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_MILLION", "1")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_MILLION", "1")
    b = Budget()
    b.reserve_llm([("human", "a" * 100)])
    with pytest.raises(BudgetExceeded, match="money_reservation"):
        b.reserve_llm([("human", "a" * 100)])
    assert b.held_cost > 0 and b.llm_calls == 1


def test_one_repair_per_request():
    b = Budget()
    b.repair()
    with pytest.raises(BudgetExceeded, match="repair_limit"):
        b.repair()
