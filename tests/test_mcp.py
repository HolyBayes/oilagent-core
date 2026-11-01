import json

from starlette.testclient import TestClient

from analyst.mcp_server import BearerGate, create_server


def test_http_bearer_gate_and_health():
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
        assert json.loads(result["content"][0]["text"])["stage"] == "integration_prototype"


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
        assert names == {"propose_change", "get_diff", "run_checks", "request_review", "get_status"}
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
