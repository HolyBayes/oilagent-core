"""Real Ouroboros MCPManager → two local HTTP services. No mock transport or model."""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from analyst.config import configured_path, evolution_repo
from analyst.evolution import SEED_SKILL

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow configured model calls")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    if args.live:
        from analyst.config import model_ready

        if not model_ready():
            parser.error("--live requires configured model credentials or a local endpoint")
    upstream = configured_path("OUROBOROS_PATH", "../workspace/upstream/ouroboros")
    skill_source = evolution_repo() / "ouroboros_skills/oilgas_analyst"
    if not skill_source.is_dir():
        # Smoke must also work before the evolution checkout has been seeded.
        skill_source = SEED_SKILL.parent
    pin = json.loads((ROOT / "config/ouroboros-pin.json").read_text())
    actual = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != pin["commit"]:
        raise RuntimeError("Ouroboros checkout does not match pinned SHA")
    subprocess.run(
        ["git", "-C", str(upstream), "diff", "--exit-code", "HEAD"], check=True, capture_output=True
    )
    run = ROOT / "workspace/smoke" / uuid4().hex
    run.mkdir(parents=True)
    os.environ.update(
        {
            "OUROBOROS_APP_ROOT": str(run / "ouroboros"),
            "OUROBOROS_DATA_DIR": str(run / "ouroboros/data"),
            "OUROBOROS_REPO_DIR": str(upstream),
        }
    )
    sys.path.insert(0, str(upstream))
    from ouroboros.mcp_client import MCPManager
    from ouroboros.skill_loader import load_skill

    child_env = {
        **os.environ,
        "WORKSPACE_PATH": str(run / "runtime"),
        "EVOLUTION_REPO_PATH": str(run / "runtime/evolution"),
    }
    if not args.live:
        # Empty env values keep load_dotenv from restoring live credentials.
        child_env.update(
            GIGACHAT_CREDENTIALS="", LLM_API_KEY="", LLM_MODEL="", LLM_PROVIDER="gigachat"
        )
    processes, handles, settings_rows, events = [], [], [], []
    try:
        for kind in ["analyst", "evolution"]:
            port, token = free_port(), secrets.token_urlsafe(32)
            env = {**child_env, f"{kind.upper()}_MCP_TOKEN": token}
            log = (run / f"{kind}.log").open("w")
            handles.append(log)
            proc = subprocess.Popen(
                [sys.executable, "-m", "analyst.mcp_server", kind, "--port", str(port)],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            processes.append(proc)
            url = f"http://127.0.0.1:{port}/mcp"
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError(f"{kind} exited; inspect {log.name}")
                try:
                    response = httpx.get(url, timeout=0.5, trust_env=False)
                    if response.status_code == 401:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError(f"{kind} startup timeout")
            settings_rows.append(
                {
                    "id": kind,
                    "name": f"OilAgent {kind}",
                    "enabled": True,
                    "transport": "streamable_http",
                    "url": url,
                    "auth_header": "Authorization",
                    "auth_token": f"Bearer {token}",
                }
            )
            events.append({"service": kind, "unauthorized_status": 401})
        manager = MCPManager()
        assert (
            httpx.get(
                settings_rows[1]["url"],
                headers={"Authorization": settings_rows[0]["auth_token"]},
                timeout=2,
                trust_env=False,
            ).status_code
            == 401
        )
        events.append({"cross_service_token_status": 401})
        manager.reconfigure(
            {"MCP_ENABLED": True, "MCP_TOOL_TIMEOUT_SEC": 60, "MCP_SERVERS": settings_rows}
        )
        for row in settings_rows:
            listing = manager.refresh_server(row["id"])
            if not listing["ok"] or not listing["published"]:
                raise RuntimeError(f"Discovery failed: {listing}")
            events.append({"listing": listing})

        def call(service, tool, arguments):
            text = manager.call_tool(f"mcp_{service}__{tool}", arguments)
            body = text.partition("\n\n")[2]
            if "MCP_TOOL_ERROR" in body or "MCP_TOOL_TIMEOUT" in body:
                raise RuntimeError(f"{tool} failed: {body}")
            value, _ = json.JSONDecoder().raw_decode(body)
            events.append({"service": service, "tool": tool, "result": value})
            return value

        assert call("analyst", "health", {})["langgraph"]
        answer = call("analyst", "answer_question", {"question": "Спрогнозируй Brent на 3 месяца"})
        assert answer["request_id"] and answer["status"] == (
            "forecasted" if args.live else "insufficient_evidence"
        )
        forecast = call("analyst", "forecast_brent", {"horizon_months": 3, "as_of": "2025-10-01"})
        assert {"ARIMA", "ETS"} <= forecast["forecasts"].keys()
        assert all(len(forecast["forecasts"][m]["points"]) == 3 for m in ["ARIMA", "ETS"])
        baseline = call("evolution", "get_status", {})
        proposal = {
            "base_sha": baseline["base_sha"],
            "artifact": "policies/retrieval.json",
            "policy": {"comparison_strategy": "per_publisher", "top_k_per_publisher": 2},
            "rationale": "Cover both publishers in the synthetic comparison fixture",
            "trace_id": answer["request_id"],
            "idempotency_key": "transport-smoke-1",
        }
        candidate = call("evolution", "propose_change", proposal)
        assert call("evolution", "propose_change", proposal) == candidate
        refused = manager.call_tool(
            "mcp_evolution__propose_change",
            {**proposal, "artifact": "../core.py", "idempotency_key": "unsafe-path"},
        )
        assert "MCP_TOOL_ERROR" in refused
        events.append({"unsafe_path_rejected_over_mcp": True})
        cid = {"candidate_id": candidate["candidate_id"]}
        assert call("evolution", "get_diff", cid)["diff"]
        assert call("evolution", "run_checks", cid)["checks"]["passed"]
        review = call("evolution", "request_review", cid)
        if not args.live:
            assert review["status"] == "REVIEW_BLOCKED" and "critic" not in review
        else:
            assert answer["route"], "Live router did not return a typed route"
            assert review["status"] == "REVIEWED_UNRELEASED", "Live critic did not complete"
        assert not call("evolution", "get_status", cid)["release_available"]

        drive = run / "ouroboros/data"
        payload = drive / "skills/external/oilgas_analyst"
        shutil.copytree(skill_source, payload)
        skill = load_skill(payload, drive)
        assert skill and not skill.load_error, getattr(skill, "load_error", "missing skill")
        assert (
            not skill.enabled and not skill.review.gate_for(skill.content_hash)["executable_review"]
        )
        events.append(
            {
                "skill": skill.name,
                "content_hash": skill.content_hash,
                "stage": "upstream loader recognizes external disk payload; review pending",
                "enabled": skill.enabled,
            }
        )
        report = {
            "ouroboros_sha": actual,
            "live_model_requested": args.live,
            "transport": "real streamable_http via unmodified Ouroboros MCPManager",
            "autonomous_agent_run": False,
            "release_available": False,
            "events": events,
        }
        (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "report": str(run / "report.json"),
                    "live_model_requested": args.live,
                    "autonomous_agent_run": False,
                }
            )
        )
    finally:
        for proc in processes:
            proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
