import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from analyst import graph as pipeline
from analyst.budget import Budget, BudgetExceeded, current_budget
from analyst.contracts import ReportClaim, ReportDraft, Route
from analyst.evidence import compare_claims
from analyst.scenario import supply_cut_scenario


@pytest.fixture(autouse=True)
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces"))
    monkeypatch.setenv("RELEASE_PATH", str(tmp_path / "releases"))


@pytest.fixture
def sources():
    report = dict(
        source_id="R1",
        kind="report",
        publisher="EIA",
        title="EIA",
        page=5,
        text="Historical oil fact.",
        published_at="2025-10-07",
        url="https://eia.gov/a.pdf",
        numeric_verified=True,
    )
    web = dict(
        source_id="W1",
        kind="web",
        publisher="eia.gov",
        title="EIA news",
        text="Fresh oil fact.",
        published_at="2026-11-01",
        retrieved_at="2026-11-01",
        url="https://eia.gov/news",
        numeric_verified=True,
    )
    return report, web


def test_hybrid_keeps_sources_and_dates(sources, monkeypatch):
    report, web = sources
    monkeypatch.setattr(pipeline, "model_ready", lambda: True)
    monkeypatch.setattr(
        pipeline, "ReportIndex", lambda: SimpleNamespace(search=lambda *a, **k: [report])
    )
    monkeypatch.setattr(pipeline, "search_web", lambda *a, **k: {"evidence": [web], "warnings": []})

    def invoke(schema, messages):
        if schema is Route:
            return Route(
                intent="domain_qa",
                freshness_required=True,
                hybrid=True,
                metric="price",
                reference_period="2026",
                report_query="historical",
                web_query="current gas news",
            ), {}
        requirements = json.loads(messages[1][1])["requirements"]
        assert not requirements.get("report_query") and not requirements.get("web_query")
        assert not requirements.get("metric") and not requirements.get("reference_period")
        return ReportDraft(
            abstain=False,
            claims=[
                ReportClaim(text=s["text"], quote=s["text"], source_id=s["source_id"])
                for s in json.loads(messages[1][1])["reports"]
            ],
        ), {}

    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    result = pipeline.answer_question("Сопоставь отчёт и свежие новости")
    assert result["status"] == "answered"
    assert {"R1", "W1"} == {s["source_id"] for s in result["evidence"]}
    assert "2025-10-07" in result["answer"] and "2026-11-01" in result["answer"]


def test_invalid_claim_gets_one_repair_and_partial(sources, monkeypatch):
    calls = []
    report, _ = sources

    def broken(*args):
        calls.append(1)
        return ReportDraft(
            abstain=False,
            claims=[
                ReportClaim(text="supported", quote=report["text"], source_id="R1"),
                ReportClaim(text="fake", quote="fake", source_id="R99"),
            ],
        ), {}

    monkeypatch.setattr(pipeline, "invoke_structured", broken)
    result = pipeline.respond(
        {
            "question": "test",
            "route": {"intent": "domain_qa", "freshness_required": False},
            "evidence": [report],
        }
    )
    assert len(calls) == 2 and result["status"] == "partial"
    assert len(result["claims"]) == 1


def test_session_resolves_followup_without_sharing_other_session(monkeypatch):
    routed = []
    monkeypatch.setattr(pipeline, "model_ready", lambda: True)

    def invoke(schema, messages):
        routed.append(json.loads(messages[1][1]))
        return Route(intent="out_of_scope", freshness_required=False), {}

    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    sid = str(uuid4())
    first = pipeline.answer_question("Первый вопрос", sid)
    pipeline.answer_question("А теперь другой?", sid)
    pipeline.answer_question("Третий вопрос", str(uuid4()))
    assert routed[1]["prior_questions"] == [{"question": "Первый вопрос"}]
    assert not routed[2]["prior_questions"]
    assert first["session_id"] == sid and first["trace_file"].endswith(".json")


def test_scenario_sensitivity_and_validation():
    params = dict(
        initial_price=70,
        supply_mbd=100,
        cut_mbd=2,
        demand_elasticity=[-0.3, -0.1],
        supply_elasticity=[0, 0.1],
        assumptions="Все параметры явно заданы пользователем.",
    )
    result = supply_cut_scenario(params)
    assert 70 < result["price_range"][0] < result["price_range"][1]
    with pytest.raises(ValueError):
        supply_cut_scenario({**params, "cut_mbd": 100})
    with pytest.raises(ValueError):
        supply_cut_scenario({**params, "demand_elasticity": [0, 0.1]})


def test_budget_stops_before_extra_effect(monkeypatch):
    monkeypatch.setenv("REQUEST_MAX_TOOLS", "1")
    b = Budget()
    b.tool("first")
    with pytest.raises(BudgetExceeded, match="tool_calls"):
        b.tool("second")
    monkeypatch.setenv("REQUEST_MAX_LLM_CALLS", "0")
    token = current_budget.set(b)
    try:
        with pytest.raises(BudgetExceeded):
            b.reserve_llm([("human", "hello")])
    finally:
        current_budget.reset(token)


def test_comparison_requires_same_definitions():
    common = dict(
        metric="demand growth",
        geography="global",
        unit="mb/d",
        period="2026",
        vintage="2025-10",
        observation_type="forecast",
        kind="fact",
    )
    a = {**common, "source_id": "R1", "value": "1.3"}
    b = {**common, "source_id": "R2", "value": "0.9"}
    result, warning = compare_claims([a, b])
    assert not warning and result["value"] == "0.4"
    assert compare_claims([a, {**b, "unit": "USD/bbl"}])[1]


def test_hybrid_preserves_report_answer_when_web_model_is_unavailable(sources, monkeypatch):
    report, web = sources

    def invoke(schema, messages):
        rows = json.loads(messages[1][1])["reports"]
        if rows[0]["source_id"].startswith("W"):
            raise TimeoutError("private transport message")
        return ReportDraft(
            abstain=False,
            claims=[ReportClaim(text=report["text"], quote=report["text"], source_id="R1")],
        ), {}

    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    result = pipeline.respond(
        {
            "question": "Исторический отчёт, а затем новости",
            "route": {"intent": "domain_qa", "hybrid": True, "freshness_required": True},
            "evidence": [report, web],
            "report_evidence": [report],
        }
    )
    assert result["status"] == "partial" and result["claims"][0]["source_id"] == "R1"
    assert "private transport message" not in json.dumps(result)


def test_qa_model_outage_returns_checked_excerpt(sources, monkeypatch):
    report, _ = sources
    monkeypatch.setattr(pipeline, "model_ready", lambda: True)
    monkeypatch.setattr(
        pipeline, "ReportIndex", lambda: SimpleNamespace(search=lambda *a, **k: [report])
    )

    def invoke(schema, messages):
        if schema is Route:
            return Route(intent="domain_qa", freshness_required=False), {}
        raise TimeoutError("private failed request")

    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    result = pipeline.answer_question("Исторический факт из отчёта")
    assert result["status"] == "partial"
    assert result["claims"][0]["kind"] == "excerpt"
    assert result["claims"][0]["source_id"] == "R1"
    assert "private failed request" not in json.dumps(result)


def test_comparison_normalizes_units_periods_and_monthly_vintages():
    common = dict(
        kind="fact",
        metric="oil demand growth",
        geography="global",
        period="2026-H1",
        vintage="2025-10",
        observation_type="forecast",
    )
    a = {**common, "source_id": "R1", "value": "1.3", "unit": "mb/d"}
    b = {
        **common,
        "source_id": "R2",
        "value": "900",
        "unit": "thousand barrels per day",
        "geography": "world",
        "period": "H1 2026",
        "vintage": "2025-10-07",
    }
    result, warning = compare_claims([a, b])
    assert not warning and result["value"] == "0.400" and result["unit"] == "mb/d"


def test_numeric_verifier_preserves_negative_sign():
    from analyst.evidence import validate_claims

    source = {"source_id": "R1", "text": "Growth was 1.3 in 2026.", "numeric_verified": True}
    draft = ReportDraft(
        abstain=False,
        claims=[ReportClaim(text="Growth was -1.3 in 2026", source_id="R1", quote=source["text"])],
    )
    assert validate_claims(draft, [source]) == ([], ["unverified_number"])
