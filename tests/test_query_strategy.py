import copy
import json

import pytest

from analyst.code_packages import SLOTS, artifact, seed_source
from analyst.method_contracts import validate
from analyst.quality import support_score
from analyst.seeds.implementations.query_strategy import run


def test_strategy_contract_rejects_unbounded_calls_weights_and_fake_sources():
    request = {"phase": "expand"}
    plan = run({"phase": "expand", "query": "EIA", "generated": {"hypothetical_document": "oil"}})
    for bad in [
        {**plan, "searches": plan["searches"] * 4},
        {**plan, "fusion_k": 0},
        {**plan, "sources": [{"text": "invented"}]},
    ]:
        with pytest.raises(ValueError):
            validate("query_strategy", request, bad)
    for weight in [0, -1, float("inf"), float("nan")]:
        bad = copy.deepcopy(plan)
        bad["searches"][0]["probes"][0]["weight"] = weight
        with pytest.raises(ValueError):
            validate("query_strategy", request, bad)
    with pytest.raises(ValueError):
        validate("query_strategy", {"phase": "plan"}, {"prompt": "x" * 2001})
    with pytest.raises(ValueError):
        validate("query_strategy", {"phase": "fuse", "rows": [{}]}, [0, 0])


def test_score_requires_complete_support_and_rewards_earlier_quotes():
    case = {"requirements": [{"publisher": "EIA", "page": 4, "quote": "Brent 52"}]}
    relevant = {"publisher": "EIA", "page": 4, "text": "Brent 52"}
    other = {"publisher": "EIA", "page": 3, "text": "Oil"}
    assert support_score(case, [relevant, other]) == 1
    assert support_score(case, [other, relevant]) == 0.5
    assert support_score(case, [other]) == 0


def test_candidate_strategy_is_scored_after_full_retrieval_without_llm(monkeypatch):
    from analyst import code_evaluation as evaluator
    from analyst import hyde, rag
    from analyst.method_runtime import source_for

    prompts = []

    class Index:
        def search(self, query, **kwargs):
            source = source_for("query_strategy")
            # A fake retriever models both candidates; no candidate code runs on the host.
            prompts.append(source)
            dataset = json.loads((evaluator.CORE_ROOT / "data/rag_eval.json").read_text())
            hyde.replay_probes.get()(query, dataset["prompt"], "gigachat", dataset["model"])
            return []

    monkeypatch.setattr(rag, "ReportIndex", Index)
    monkeypatch.setattr(
        hyde, "invoke_structured", lambda *a, **kw: pytest.fail("Unexpected paid call")
    )
    candidate = "def run(request): return {}"
    values = evaluator.score("query_strategy", candidate, {})
    assert len(values) == 13 and values == [0] * 13
    assert set(prompts) == {candidate}
    assert hyde.replay_probes.get() is None


def test_changed_prompt_cannot_use_unrelated_replay_or_call_model(monkeypatch):
    from analyst import code_evaluation as evaluator
    from analyst import hyde, rag

    class Index:
        def search(self, query, **kwargs):
            return hyde.replay_probes.get()(query, "changed prompt", "gigachat", "GigaChat-2")

    monkeypatch.setattr(rag, "ReportIndex", Index)
    monkeypatch.setattr(
        hyde, "invoke_structured", lambda *a, **kw: pytest.fail("Unexpected paid call")
    )
    with pytest.raises(ValueError, match="No approved probe fixture"):
        evaluator.score("query_strategy", seed_source("query_strategy"), {})
    assert hyde.replay_probes.get() is None


def test_strategy_is_versioned_with_rag_and_can_be_proposed(tmp_path):
    from analyst.code_packages import propose, snapshot
    from analyst.evolution import Evolution

    backend = Evolution(tmp_path)
    base = backend.baseline()["base_sha"]
    assert SLOTS["query_strategy"] == "report_rag"
    candidate = seed_source("query_strategy") + "\n"
    state = propose(backend, base, "query_strategy", candidate, "test", "fixture", "query-1")
    assert state["artifact"] == artifact("query_strategy")
    assert snapshot(backend, state["candidate_sha"], "query_strategy")["source"] == candidate
    assert backend.baseline()["base_sha"] == base
    assert "ouroboros_skills/report_rag/SKILL.md" in state["artifacts"]
