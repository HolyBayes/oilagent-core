import json

from starlette.testclient import TestClient

from analyst.mcp_server import BearerGate, create_server


def test_http_bearer_gate_and_health(monkeypatch):
    monkeypatch.setenv("WEB_ENABLED", "false")
    token = "test-analyst-token-with-more-than-24-chars"
    server = create_server("analyst", "127.0.0.1", 8011)
    with TestClient(
        BearerGate(server.streamable_http_app(), token), base_url="http://127.0.0.1:8011"
    ) as client:
        assert client.post("/mcp").status_code == 401
        assert client.post("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "health", "arguments": {}},
            },
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert not result.get("isError")
        assert json.loads(result["content"][0]["text"])["stage"] == "report_rag"
        response = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "search_web_sources", "arguments": {"query": "oil news"}},
            },
        )
        result = response.json()["result"]
        assert not result.get("isError")
        assert json.loads(result["content"][0]["text"])["warnings"] == ["web_disabled"]


def test_evolution_tool_catalog_has_no_release_or_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("EVOLUTION_REPO_PATH", str(tmp_path / "evolution"))
    server = create_server("evolution", "127.0.0.1", 8012)
    with TestClient(
        BearerGate(server.streamable_http_app(), "token"), base_url="http://127.0.0.1:8012"
    ) as client:
        response = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer token",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        names = {t["name"] for t in response.json()["result"]["tools"]}
        assert names == {
            "propose_change",
            "get_diff",
            "run_checks",
            "request_review",
            "get_status",
            "propose_skill",
            "read_skill",
            "read_code",
            "propose_code",
        }
        wire = json.dumps(response.json()["result"]["tools"])
        assert '"$ref"' not in wire and '"$defs"' not in wire and '"anyOf"' not in wire
        args = {
            "base_sha": "0" * 40,
            "artifact": "policies/retrieval.json",
            "policy": {"allow_unverified_sources": True},
            "rationale": "bad policy",
            "trace_id": "test",
            "idempotency_key": "unsafe-schema",
        }
        rejected = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer token",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "propose_change", "arguments": args},
            },
        )
        assert rejected.json()["result"]["isError"]


def test_forecast_asset_contract_and_recorded_direct_result(tmp_path, monkeypatch):
    import analyst.mcp_server as module

    monkeypatch.setenv("TRACE_PATH", str(tmp_path))
    calls = []

    def calculate(*args):
        calls.append(args)
        return {"data_cache": {"complete": True}}

    monkeypatch.setattr(module, "forecast_brent", calculate)
    monkeypatch.setattr(module, "render_forecast", lambda result: "Calculated ARIMA/ETS")
    server = create_server("analyst", "127.0.0.1", 8011)
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:8011") as client:
        headers = {"Accept": "application/json, text/event-stream"}

        def call(arguments):
            return client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "forecast", "arguments": arguments},
                },
            ).json()["result"]

        assert call({"asset": "wti"})["isError"]
        assert calls == []
        result = call(
            {
                "asset": "brent",
                "horizon_months": 2,
                "start_date": "2015-01-01",
                "end_date": "2025-12-31",
            }
        )
        assert not result.get("isError")
        payload = json.loads(result["content"][0]["text"])
        assert payload["asset"] == "brent" and payload["answer"] == "Calculated ARIMA/ETS"
        recorded = json.loads((tmp_path / (payload["request_id"] + ".json")).read_text())
        assert recorded["arguments"]["asset"] == "brent"
        assert calls == [(2, "", "2015-01-01", "2025-12-31")]
