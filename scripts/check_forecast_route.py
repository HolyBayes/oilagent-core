"""One optional model choice followed by a real authenticated Forecast MCP call."""

import argparse
import json
import os
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from analyst.config import CORE_ROOT, chat_model
from analyst.provider_lock import provider_slot


def check(live):
    load_dotenv(CORE_ROOT / ".env", override=False)
    report = {
        "live": live,
        "model": os.getenv("GIGACHAT_MODEL"),
        "native_ui_delegation": False,
        "transport": "compact skill context → model → HTTP MCP",
    }
    path = CORE_ROOT / "workspace" / ("forecast-route-" + uuid4().hex + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)

    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    with httpx.Client(
        base_url="http://127.0.0.1:" + os.getenv("ANALYST_PORT", "8011"),
        trust_env=False,
        timeout=60,
        headers={
            "Authorization": "Bearer " + os.environ["ANALYST_MCP_TOKEN"],
            "Accept": "application/json, text/event-stream",
        },
    ) as client:

        def rpc(method, params):
            response = client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            response.raise_for_status()
            result = response.json()["result"]
            if result.get("isError"):
                raise ValueError("MCP returned a tool error")
            return result

        catalog = rpc("tools/list", {})["tools"]
        forecast = next(t for t in catalog if t["name"] == "forecast")
        assert "asset" in forecast["inputSchema"]["required"]
        report["catalog"] = [t["name"] for t in catalog]
        save()
        if live:
            if os.getenv("LLM_PROVIDER", "gigachat") != "gigachat":
                raise ValueError("OpenAI/local live probes are intentionally excluded")
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_analyst__" + t["name"],
                        "description": t["description"],
                        "parameters": t["inputSchema"],
                    },
                }
                for t in catalog
            ]
            skill = (CORE_ROOT / "src/analyst/seeds/oil_forecast/SKILL.md").read_text()
            with provider_slot():
                message = (
                    chat_model()
                    .bind_tools(tools)
                    .invoke(
                        [
                            ("system", skill),
                            (
                                "human",
                                "Рассчитай новый ARIMA/ETS прогноз Brent на 2 месяца: "
                                "as_of 2025-10-01, история 2015-01-01 — 2025-09-30.",
                            ),
                        ]
                    )
                )
            report.update(
                calls=message.tool_calls,
                usage=dict(message.usage_metadata or {}),
                model_text=message.content,
            )
            save()
            call = message.tool_calls[0] if len(message.tool_calls) == 1 else {}
            if (
                call.get("name") != "mcp_analyst__forecast"
                or call.get("args", {}).get("asset", "").casefold() != "brent"
                or call.get("args", {}).get("horizon_months") != 2
            ):
                raise ValueError("Unexpected model choice; retained in " + str(path))
            result = rpc("tools/call", {"name": "forecast", "arguments": call["args"]})
            result = json.loads(result["content"][0]["text"])
            report.update(
                status=result["status"],
                request_id=result["request_id"],
                models=list(result.get("forecasts", {})),
                data_cache=result.get("data_cache"),
            )
            save()
            assert {"ARIMA", "ETS"} <= set(report["models"])
    print(
        json.dumps(
            {
                "report": str(path),
                "model": report["model"],
                "status": report.get("status"),
                "usage": report.get("usage"),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    check(parser.parse_args().live)
