"""Compact, explicit live code-author/check/critic probe; never activates a candidate."""

import argparse
import json
import os
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from analyst.config import CORE_ROOT, chat_model
from analyst.method_runtime import run
from analyst.provider_lock import provider_slot
from analyst.traces import save_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument(
        "--retry", action="store_true", help="One correction using the previous measured failure"
    )
    args = parser.parse_args()
    assert args.live
    load_dotenv(CORE_ROOT / ".env", override=False)
    previous_path = CORE_ROOT / "workspace/code-workflow-evidence.json"
    previous = json.loads(previous_path.read_text()) if args.retry else None
    request_id = previous["trace_id"] if previous else str(uuid4())
    fixture = {
        "query": "oil supply",
        "rows": [
            {"priority": 0, "title": "Electricity", "text": "Solar electricity statistics"},
            {"priority": 1, "title": "Oil supply", "text": "Oil supply and OPEC production update"},
        ],
    }
    before = run("search_strategy", fixture)
    save_trace(
        {
            "request_id": request_id,
            "kind": "code_ranking_probe",
            "synthetic": True,
            "question": fixture["query"],
            "inputs": fixture,
            "actual_order": before,
            "failure": "Source priority places an irrelevant publication first",
        }
    )
    report = {
        "trace_id": request_id,
        "author": "compact GigaChat tool call, not native UI",
        "fixture": True,
        "live_author": True,
        "activation": False,
    }
    with httpx.Client(
        base_url="http://127.0.0.1:" + os.getenv("EVOLUTION_PORT", "8012"),
        headers={
            "Authorization": "Bearer " + os.environ["EVOLUTION_MCP_TOKEN"],
            "Accept": "application/json, text/event-stream",
        },
        trust_env=False,
        timeout=130,
    ) as client:

        def rpc(method, params):
            r = client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            r.raise_for_status()
            result = r.json()["result"]
            if result.get("isError"):
                raise ValueError(result["content"][0]["text"])
            return result

        def call(name, args):
            return json.loads(
                rpc("tools/call", {"name": name, "arguments": args})["content"][0]["text"]
            )

        committed = call("read_code", {"slot": "search_strategy"})
        tool = next(t for t in rpc("tools/list", {})["tools"] if t["name"] == "propose_code")
        schema = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"],
            },
        }
        prompt = (
            "Create one propose_code candidate to improve search_strategy relevance. "
            "Return exactly one tool call. Python exports run(request); request has query and rows "
            "with title/text/priority. Return a permutation of all input row indices. "
            "Use case-insensitive query token overlap in title+text, source priority for ties. "
            "No networking, filesystem, dynamic evaluation, external dependencies or case-specific "
            "answers. Preserve all rows. Supply valid Python source with actual line breaks. "
            f"base_sha={committed['source_commit']}, slot=search_strategy, trace_id={request_id}, "
            f"idempotency_key=live-code-{'retry-' if previous else ''}{request_id}. "
            f"Observed development fixture (synthetic): {json.dumps(fixture)}; returned {before}."
        )
        if previous:
            prompt += (
                " The previous candidate returned source priority order and had zero gain. "
                "Correct it: tokenize query and each row title+text with re.findall, "
                "compute intersection size, sort indices by tuple "
                "(-overlap_count, priority, index). "
                "Query relevance MUST precede priority. Do not copy the old source. "
                "For the observed fixture the oil supply row at index 1 must come first."
            )
        with provider_slot():
            result = chat_model().bind_tools([schema]).invoke([("human", prompt)])
        report["author_usage"] = dict(result.usage_metadata or {})
        if len(result.tool_calls) != 1 or result.tool_calls[0]["name"] != "propose_code":
            raise ValueError("Expected one propose_code tool call")
        state = call("propose_code", result.tool_calls[0]["args"])
        report["candidate_id"] = state["candidate_id"]
        path = CORE_ROOT / "workspace" / "code-workflow-evidence.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        state = call("run_checks", {"candidate_id": state["candidate_id"]})
        report["checks"] = state.get("quality_checks", {})
        if report["checks"].get("passed"):
            state = call("request_review", {"candidate_id": state["candidate_id"]})
        report.update(
            status=state["status"],
            candidate_sha=state["candidate_sha"],
            critic=state.get("critic"),
            critic_usage=state.get("critic_usage"),
        )
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
