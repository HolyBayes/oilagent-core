"""Compact model/MCP probe; no full native UI run, installation or release."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from analyst.config import CORE_ROOT, chat_model, workspace
from analyst.evolution import Evolution
from analyst.mcp_server import create_server
from analyst.provider_lock import provider_slot
from analyst.traces import save_trace


def choose(tools, prompt):
    with provider_slot():
        result = (
            chat_model()
            .bind_tools(tools)
            .invoke(
                [
                    (
                        "system",
                        "Use the appropriate MCP tool. Do not claim execution before its result.",
                    ),
                    ("human", prompt),
                ]
            )
        )
    if len(result.tool_calls) != 1:
        raise ValueError("Expected one model-selected MCP tool")
    return result.tool_calls[0], dict(result.usage_metadata or {})


async def catalog(server):
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema},
        }
        for t in await server.list_tools()
    ]


def check(live, resume=None):
    from dotenv import load_dotenv

    load_dotenv(CORE_ROOT / ".env", override=False)
    root = Path(resume).resolve() if resume else workspace() / "skill-probes" / uuid4().hex
    if not root.is_relative_to((workspace() / "skill-probes").resolve()):
        raise ValueError("Resume must be inside the probe workspace")
    os.environ.update(WORKSPACE_PATH=str(root), EVOLUTION_REPO_PATH=str(root / "evolution"))
    os.environ["TRACE_PATH"] = str(root / "traces")
    backend = Evolution(root)
    analyst = create_server("analyst", "127.0.0.1", 0)
    evolution = create_server("evolution", "127.0.0.1", 0)
    analyst_tools = asyncio.run(catalog(analyst))
    evolution_tools = asyncio.run(catalog(evolution))
    report = {
        "live": live,
        "transport": "compact model → in-process real MCP",
        "native_ui_or_delegation_proof": False,
        "skills": backend.baseline()["skills"],
    }
    path = root / "evidence.json"
    if resume:
        report = json.loads(path.read_text())

    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    save()
    if live:
        if "forecast" not in report:
            call, usage = choose(
                analyst_tools, "Рассчитай новый ARIMA/ETS прогноз Brent на 2 месяца."
            )
            if call["name"] != "forecast" or call["args"].get("horizon_months") != 2:
                raise ValueError("Model failed to select forecast with the requested horizon")
            asyncio.run(analyst.call_tool(call["name"], call["args"]))
            traces = list((root / "traces").glob("*.json"))
            result = json.loads(traces[0].read_text())
            if result.get("status") not in {"forecasted", "partial"}:
                raise ValueError("Forecast calculation failed")
            report["forecast"] = {
                "tool": call["name"],
                "status": result["status"],
                "request_id": result["request_id"],
                "usage": usage,
            }
            save()
        trace_id = str(uuid4())
        save_trace(
            {
                "request_id": trace_id,
                "kind": "integration_probe",
                "question": "Create an instruction skill for calculated Brent forecasts",
            }
        )
        sha = backend.baseline()["base_sha"]
        call, author_usage = choose(
            evolution_tools,
            (
                "Create a NEW instruction skill brent_forecast, capability forecast, "
                f"base_sha {sha}, "
                f"trace_id {trace_id}, idempotency_key live-new-forecast. Use propose_skill. "
                "Supply description, version 0.1.0 and instructions as Markdown body only. "
                "Do not include YAML, JSON, code fences or escaped newline sequences. "
                "It must use mcp_analyst__forecast for new ARIMA/ETS with user horizon_months "
                "and asset=brent, optional ISO as_of/start_date/end_date; no CSV upload. "
                "Preserve both model "
                "tables, nominal 80% intervals, daily EIA source. For supply_cut ask for missing "
                "P0/Q0/cut/elasticities. Report forecasts are report_rag, not new calculations. "
                "No executable payload, permissions, release or always_in_context."
            ),
        )
        if call["name"] != "propose_skill":
            raise ValueError("Model did not propose a skill")
        report.setdefault("author_attempts", []).append({"call": call, "usage": author_usage})
        save()
        try:
            asyncio.run(evolution.call_tool(call["name"], call["args"]))
        except Exception as exc:
            report["author_attempts"][-1]["validation_error"] = str(exc)
            save()
            call, repair_usage = choose(
                evolution_tools,
                "Repair the rejected proposal according to its validation error. "
                "Use typed description, version string 0.1.0 and Markdown instructions. "
                + json.dumps({"proposal": call, "error": str(exc)}, ensure_ascii=False),
            )
            if call["name"] != "propose_skill":
                raise ValueError("Repair did not propose a skill")
            report["author_attempts"].append({"call": call, "usage": repair_usage})
            save()
            asyncio.run(evolution.call_tool(call["name"], call["args"]))
        state = json.loads(next(backend.states.glob("*.json")).read_text())
        report["candidate"] = state
        save()
        checked = backend.checks(state["candidate_id"], real=True)
        report["candidate"] = checked
        save()
        if checked["quality_checks"]["passed"]:
            checked = backend.review(state["candidate_id"])
        report.update(
            author_usage=author_usage,
            candidate=checked,
        )
    save()
    print(
        json.dumps(
            {
                "report": str(path),
                "live": live,
                "forecast": report.get("forecast"),
                "candidate_status": report.get("candidate", {}).get("status"),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--resume")
    args = parser.parse_args()
    check(args.live, args.resume)
