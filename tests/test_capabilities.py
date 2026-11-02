import pytest
from starlette.testclient import TestClient

from analyst import capabilities
from analyst.capabilities import CapabilityDisabled
from analyst.mcp_server import create_server


def disabled(monkeypatch):
    monkeypatch.setattr(capabilities, "native_states", lambda: {})


def test_forecast_and_graph_cannot_bypass_disabled_skill(monkeypatch):
    import analyst.forecast as forecast
    from analyst.graph import respond

    disabled(monkeypatch)
    monkeypatch.setattr(
        forecast, "_forecast_brent", lambda *a, **k: pytest.fail("Calculation executed")
    )
    with pytest.raises(CapabilityDisabled, match="oil_forecast"):
        forecast.forecast_brent(3)
    result = respond({"question": "Прогноз Brent", "route": {"intent": "forecast"}})
    assert result["status"] == "capability_disabled"
    assert "oil_forecast" in result["answer"]


def test_disabled_coordinator_blocks_router_before_llm(monkeypatch):
    from analyst import graph

    disabled(monkeypatch)
    monkeypatch.setattr(graph, "_answer_question", lambda *a: pytest.fail("Router executed"))
    with pytest.raises(CapabilityDisabled):
        graph.answer_question("forecast")


def test_unknown_tool_fails_registration_instead_of_becoming_public():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("test")
    capabilities.install_tool_gates(server, "analyst")
    with pytest.raises(ValueError, match="no capability owner"):
        server.tool()(lambda: None)


def test_future_slot_uses_its_declared_owner(monkeypatch):
    from analyst.code_packages import SLOTS
    from analyst.method_runtime import run_many

    monkeypatch.setitem(SLOTS, "future_method", "future_skill")
    disabled(monkeypatch)
    with pytest.raises(CapabilityDisabled, match="future_skill"):
        run_many("future_method", [{}], "def run(request): return 1")


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"enabled": False, "executable_review": True, "review_stale": False},
        {"enabled": True, "executable_review": False, "review_stale": False},
        {"enabled": True, "executable_review": True, "review_stale": True},
    ],
)
def test_disabled_missing_unreviewed_or_stale_skill_is_denied(monkeypatch, state):
    monkeypatch.setattr(capabilities, "native_states", lambda: {"module": state})
    with pytest.raises(CapabilityDisabled):
        capabilities.require_skill("module")


def test_ui_outage_fails_closed(monkeypatch):
    def unavailable():
        raise ConnectionError("offline")

    monkeypatch.setattr(capabilities, "native_states", unavailable)
    with pytest.raises(CapabilityDisabled, match="недоступно"):
        capabilities.require_skill("oil_forecast")


def test_toggle_changes_apply_without_restart(monkeypatch):
    state = {"enabled": True, "executable_review": True, "review_stale": False}
    monkeypatch.setattr(capabilities, "native_states", lambda: {"module": state})
    capabilities.require_skill("module")
    state["enabled"] = False
    with pytest.raises(CapabilityDisabled):
        capabilities.require_skill("module")


def test_all_analyst_http_entrypoints_deny_disabled_modules(monkeypatch):
    disabled(monkeypatch)
    server = create_server("analyst", "127.0.0.1", 0)
    calls = {
        "forecast": {"asset": "brent"},
        "answer_question": {"question": "Brent"},
        "supply_cut": {"inputs": {}},
        "market_quote": {},
        "search_reports": {"query": "oil"},
        "search_web_sources": {"query": "oil"},
        "submit_feedback": {"request_id": "fixture", "rating": 0, "comment": "fixture"},
    }
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:0") as client:
        for name, args in calls.items():
            response = client.post(
                "/mcp",
                headers={"Accept": "application/json, text/event-stream"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                },
            )
            body = response.json()["result"]
            assert body["isError"], name
            assert "отключён" in body["content"][0]["text"], (name, body)


@pytest.mark.parametrize("owner", [None, "", False])
def test_new_feature_cannot_be_accidentally_declared_public(tmp_path, monkeypatch, owner):
    import json

    config = tmp_path / "config"
    config.mkdir()
    (config / "capabilities.json").write_text(json.dumps({"analyst": {"future": owner}}))
    monkeypatch.setattr(capabilities, "CORE_ROOT", tmp_path)
    with pytest.raises(ValueError, match="Invalid capability owner"):
        capabilities.owners_for("analyst")


def test_async_modules_have_same_gate_and_keep_async_signature(monkeypatch):
    import asyncio
    import inspect

    calls = []
    state = {"enabled": True, "executable_review": True, "review_stale": False}
    monkeypatch.setattr(capabilities, "native_states", lambda: {"future": state})

    @capabilities.requires_skill("future")
    async def execute(value: int):
        calls.append(value)
        return value + 1

    assert inspect.iscoroutinefunction(execute)
    assert asyncio.run(execute(1)) == 2
    state["enabled"] = False
    with pytest.raises(CapabilityDisabled):
        asyncio.run(execute(2))
    assert calls == [1]


def test_nested_denial_is_not_reported_as_model_outage(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from analyst import graph

    for key, value in {
        "SESSION_DB_PATH": tmp_path / "sessions.sqlite3",
        "TRACE_PATH": tmp_path / "traces",
        "RELEASE_PATH": tmp_path / "releases",
    }.items():
        monkeypatch.setenv(key, str(value))
    state = {"enabled": True, "executable_review": True, "review_stale": False}
    monkeypatch.setattr(capabilities, "native_states", lambda: {"oilgas_analyst": state})
    monkeypatch.setattr(
        graph,
        "graph",
        SimpleNamespace(stream=lambda *a, **k: capabilities.require_skill("web_research")),
    )
    result = graph.answer_question("Новости о нефти")
    assert result["status"] == "capability_disabled"
    assert "web_research" in result["answer"]
    assert "module_disabled" in result["warnings"]


def test_unknown_review_freshness_is_denied(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "native_states",
        lambda: {"module": {"enabled": True, "executable_review": True, "review_stale": None}},
    )
    with pytest.raises(CapabilityDisabled):
        capabilities.require_skill("module")
