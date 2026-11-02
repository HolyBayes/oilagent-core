"""Five real native UI gateway tasks, one attempt each; preserves failures and usage."""

import json
import re
import time
from pathlib import Path

import httpx

cases = json.loads(Path("docs/lite-delivery-evidence.json").read_text())["cases"]
report = {
    "transport": "native UI /api/tasks -> Main -> HTTP MCP",
    "model": "GigaChat-2",
    "attempts_per_case": 1,
    "cases": [],
}
output = Path("docs/native-lite-delivery-evidence.json")
with httpx.Client(base_url="http://127.0.0.1:8765", trust_env=False, timeout=30) as client:
    for case in cases:
        response = client.post(
            "/api/tasks",
            json={
                "description": case["question"] + " Ответь кратко. Не делегируй.",
                "memory_mode": "empty",
                "disabled_tools": ["schedule_subagent"],
            },
        )
        response.raise_for_status()
        task_id = response.json()["task_id"]
        deadline = time.monotonic() + 240
        while True:
            response = client.get("/api/tasks/" + task_id)
            response.raise_for_status()
            task = response.json()
            if task["status"] in {"completed", "failed", "cancelled"}:
                break
            if time.monotonic() >= deadline:
                client.post("/api/tasks/" + task_id + "/cancel", json={}).raise_for_status()
                break
            time.sleep(2)
        row = {
            "case": case["case"],
            "question": case["question"],
            **{
                k: task.get(k)
                for k in [
                    "task_id",
                    "status",
                    "result",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_rounds",
                ]
            },
        }
        ids = re.findall(
            r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}", str(task.get("result", ""))
        )
        traces = []
        for request_id in ids:
            path = Path("workspace/container/traces") / (request_id + ".json")
            if path.exists():
                trace = json.loads(path.read_text())
                traces.append(
                    {
                        k: trace.get(k)
                        for k in ["request_id", "status", "answer", "warnings", "missing", "usage"]
                    }
                )
        row["analyst_traces"] = traces
        report["cases"].append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(case["case"], task["status"], [t["status"] for t in traces], flush=True)
