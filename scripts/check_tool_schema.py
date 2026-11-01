"""One compact native GigaChat function call; no full Ouroboros context or critic."""

import argparse
import asyncio
import json
import os
from uuid import uuid4

from analyst.config import chat_model, workspace
from analyst.evolution import Evolution
from analyst.mcp_server import create_server


async def check(live):
    root = workspace() / "schema-probes" / uuid4().hex
    os.environ.update(WORKSPACE_PATH=str(root), EVOLUTION_REPO_PATH=str(root / "evolution"))
    backend = Evolution(root)
    server = create_server("evolution", "127.0.0.1", 0)
    tools = await server.list_tools()
    functions = [
        {
            "name": f"mcp_evolution__{t.name}",
            "description": t.description,
            "parameters": t.inputSchema,
        }
        for t in tools
    ]
    assert not any(k in json.dumps(functions) for k in ['"$ref"', '"$defs"', '"anyOf"'])
    report = {
        "functions": [f["name"] for f in functions],
        "live": live,
        "full_ouroboros_runtime": False,
        "transport": "in_process_mcp",
    }
    if live:
        if os.getenv("LLM_PROVIDER", "gigachat") != "gigachat":
            raise ValueError("This probe checks the native GigaChat wire format")
        baseline = backend.baseline()
        prompt = (
            f"Create a candidate for policies/retrieval.json at base {baseline['base_sha']}. "
            "A pooled search returned only A when comparing publishers A and B. "
            "Choose a policy restoring publisher coverage. Use trace_id=schema-probe, "
            "idempotency_key=schema-probe-1. Call propose_change; do not claim approval."
        )
        client = chat_model()
        result = client._client.chat(
            {
                "model": client.model,
                **({"max_tokens": client.max_tokens} if client.max_tokens is not None else {}),
                "messages": [
                    {
                        "role": "system",
                        "content": "Propose only a bounded retrieval policy via tools.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "functions": functions,
                "function_call": {"name": "mcp_evolution__propose_change"},
                "temperature": 0,
            }
        )
        call = result.choices[0].message.function_call
        if not call or call.name != "mcp_evolution__propose_change":
            raise ValueError("Expected a proposal function call")
        await server.call_tool("propose_change", call.arguments)
        candidate = json.loads(next(backend.states.glob("*.json")).read_text())
        checked = backend.checks(candidate["candidate_id"])
        report.update(usage=result.usage.model_dump(), candidate=checked)
    path = root / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(path), "live": live, "usage": report.get("usage")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    asyncio.run(check(parser.parse_args().live))
