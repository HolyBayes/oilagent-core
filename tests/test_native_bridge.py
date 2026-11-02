import importlib.util

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from analyst.config import CORE_ROOT
from analyst.runtime import provider_settings


def module():
    spec = importlib.util.spec_from_file_location(
        "native_bridge", CORE_ROOT / "scripts/native_bridge.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_owned_codex_bridge_auth_tool_contract_and_usage():
    bridge = module()
    calls = []
    route = "claudexor::codex=exact-owner-selected-model"

    def chat(**kwargs):
        calls.append(kwargs)
        return (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "1",
                        "type": "function",
                        "function": {"name": "Route", "arguments": '{"intent":"forecast"}'},
                    }
                ],
            },
            {"prompt_tokens": 50, "completion_tokens": 20, "cached_tokens": 10},
        )

    app = Starlette(
        routes=[
            Route(
                "/chat/completions",
                methods=["POST"],
                endpoint=bridge.endpoint("private-token", route, chat),
            )
        ]
    )
    with TestClient(app) as client:
        payload = {
            "model": route,
            "messages": [{"role": "user", "content": "forecast"}],
            "tools": [{"type": "function", "function": {"name": "Route"}}],
            "tool_choice": {"type": "function", "function": {"name": "Route"}},
        }
        assert client.post("/chat/completions", json=payload).status_code == 401
        headers = {"Authorization": "Bearer private-token"}
        result = client.post("/chat/completions", json=payload, headers=headers)
        assert result.status_code == 200 and calls[0]["max_tokens"] is None
        assert not calls[0]["wait_for_resources"]
        assert calls[0]["tool_choice"] == payload["tool_choice"]
        assert result.json()["usage"]["total_tokens"] == 70
        assert result.json()["choices"][0]["finish_reason"] == "tool_calls"
        payload["model"] = "openai::other-model"
        assert client.post("/chat/completions", json=payload, headers=headers).status_code == 400
        assert len(calls) == 1


def test_codex_bridge_native_main_route_and_missing_usage():
    route = "claudexor::codex=exact-owner-selected-model"
    model, credentials = provider_settings(
        {
            "LLM_PROVIDER": "local",
            "LLM_MODEL": route,
            "LLM_BASE_URL": "http://ouroboros:8765/oilagent/v1",
        }
    )
    assert model == route and not credentials
    result = module().completion_response(route, {"role": "assistant", "content": "ok"}, {})
    assert "usage" not in result


def test_bridge_does_not_treat_upstream_zero_defaults_as_reported_usage():
    bridge = module()
    result = bridge.completion_response(
        "claudexor::codex=model",
        {"content": "ok"},
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reported_tokens": {"prompt_tokens": None, "completion_tokens": None},
        },
    )
    assert "usage" not in result


def test_bridge_registration_updates_the_gateway_export_used_by_server(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace

    gateway = ModuleType("ouroboros.gateway")
    router = ModuleType("ouroboros.gateway.router")
    llm = ModuleType("ouroboros.llm")
    package = ModuleType("ouroboros")
    router.collect_routes = lambda **kwargs: []
    gateway.collect_routes = lambda **kwargs: router.collect_routes(**kwargs)
    gateway.router = router
    package.gateway = gateway
    llm.LLMClient = lambda: SimpleNamespace(chat=lambda **kwargs: None)
    for name, value in [
        ("ouroboros", package),
        ("ouroboros.gateway", gateway),
        ("ouroboros.gateway.router", router),
        ("ouroboros.llm", llm),
    ]:
        monkeypatch.setitem(sys.modules, name, value)
    monkeypatch.setenv("OUROBOROS_LLM_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("LLM_BRIDGE_TOKEN", "test-token-with-more-than-24-characters")
    monkeypatch.setenv("LLM_MODEL", "claudexor::codex=model")
    module().install_model_bridge()
    assert gateway.collect_routes is router.collect_routes
    assert gateway.collect_routes()[0].path == "/oilagent/v1/chat/completions"
