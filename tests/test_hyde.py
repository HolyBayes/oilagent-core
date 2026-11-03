from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

from analyst import hyde
from analyst.budget import Budget, current_budget


@pytest.fixture
def generator(monkeypatch):
    calls = []
    monkeypatch.setattr(hyde, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("RAG_HYDE_PROVIDER", "gigachat")
    monkeypatch.setenv("RAG_HYDE_MODEL", "GigaChat-2")

    def generate(schema, messages, **kwargs):
        calls.append((messages, kwargs))
        return schema(paragraph="EIA Brent forecast: [VALUE] in 2026."), {}

    monkeypatch.setattr(hyde, "invoke_structured", generate)
    return calls


def test_default_enable_and_cache_isolated_by_query_and_model(tmp_path, monkeypatch, generator):
    monkeypatch.delenv("RAG_HYDE_ENABLED", raising=False)
    assert hyde.hyde_enabled()
    for _ in range(2):
        hyde.hypothetical_passage("EIA Brent 2026", tmp_path)
    assert len(generator) == 1
    assert generator[0][1] == {"provider": "gigachat", "model": "GigaChat-2"}
    hyde.hypothetical_passage("EIA Brent 2026", tmp_path, model="another-model")
    hyde.hypothetical_passage("OPEC Brent 2026", tmp_path)
    assert len(generator) == 3


def test_concurrent_requests_generate_once(tmp_path, generator):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: hyde.hypothetical_passage("EIA", tmp_path), range(4)))
    assert len(set(results)) == 1 and len(generator) == 1


def test_failed_generation_is_not_cached(tmp_path, monkeypatch, generator):
    generate = hyde.invoke_structured

    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(hyde, "invoke_structured", fail)
    with pytest.raises(RuntimeError):
        hyde.hypothetical_passage("EIA", tmp_path)
    monkeypatch.setattr(hyde, "invoke_structured", generate)
    hyde.hypothetical_passage("EIA", tmp_path)
    assert len(generator) == 1


def test_hyde_embedding_combines_question_and_passage(tmp_path, generator):
    calls = []

    def encode(texts, **kwargs):
        calls.extend(texts)
        return np.array([[1.0, 0.0], [0.0, 1.0]])

    vector = hyde.query_embedding("EIA 2026", SimpleNamespace(encode=encode), tmp_path)
    assert np.allclose(vector, [[2**-0.5, 2**-0.5]])
    assert calls[0] == "query: EIA 2026" and calls[1].startswith("passage: EIA")


def test_independent_model_uses_common_budget(monkeypatch, tmp_path):
    import analyst.config as config

    calls = []

    class Model:
        def invoke(self, messages):
            return {
                "raw": SimpleNamespace(usage_metadata={"input_tokens": 4, "output_tokens": 2}),
                "parsed": hyde.HypotheticalPassage(paragraph="[VALUE]"),
                "parsing_error": None,
            }

    def structured(*args, **kwargs):
        calls.append(kwargs)
        return Model()

    monkeypatch.setattr(config, "structured_model", structured)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("RAG_HYDE_PROVIDER", "gigachat")
    monkeypatch.setenv("RAG_HYDE_MODEL", "GigaChat-2")
    monkeypatch.setenv("LLM_LOCK_PATH", str(tmp_path / "provider.lock"))
    budget = Budget()
    token = current_budget.set(budget)
    try:
        hyde.hypothetical_passage("EIA", tmp_path)
        hyde.hypothetical_passage("EIA", tmp_path)
    finally:
        current_budget.reset(token)
    assert budget.llm_calls == 1 and budget.input_tokens == 4 and budget.output_tokens == 2
    assert calls == [{"include_raw": True, "provider": "gigachat", "model": "GigaChat-2"}]


def test_main_retrieval_uses_hyde_setting(monkeypatch):
    from analyst import graph

    calls = []

    class Index:
        def search(self, query, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(graph, "ReportIndex", Index)
    state = {"question": "EIA Brent 2026", "route": {"intent": "domain_qa"}}
    monkeypatch.setenv("RAG_HYDE_ENABLED", "true")
    graph.retrieve(state)
    monkeypatch.setenv("RAG_HYDE_ENABLED", "false")
    graph.retrieve(state)
    assert [call["hyde"] for call in calls] == [True, False]
