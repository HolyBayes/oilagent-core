"""Prepare or drive the full upstream runtime without changing canonical repositories."""

import argparse
import json
import subprocess
from pathlib import Path

import httpx

from analyst.runtime import isolated_env, prepare, runtime_paths


def submit_task(client, prompt_file):
    root, python = runtime_paths()
    repo = root / "repo"
    skills = client.get("/api/extensions").json()["skills"]
    target = next((s for s in skills if s["name"] == "oilgas_analyst"), {})
    if not (target.get("enabled") and target.get("executable_review")):
        raise ValueError("Enable the current reviewed oilgas_analyst skill first")
    # Bundled extensions bypass the static tool list unless disabled here.
    for skill in skills:
        if skill.get("enabled") and skill["name"] != "oilgas_analyst":
            off = client.post(
                f"/api/skills/{skill['name']}/toggle",
                json={"enabled": False, "expected_content_hash": skill["content_hash"]},
            )
            off.raise_for_status()
            if off.json().get("enabled"):
                raise ValueError("Could not disable unrelated runtime skill")
    prompt = Path(prompt_file).read_text()
    # Registry discovery must use the upstream interpreter.
    registry_code = (
        "import json,os; from pathlib import Path; "
        "from ouroboros.tools.registry import ToolRegistry; "
        "r=ToolRegistry(Path(os.environ['OUROBOROS_REPO_DIR']),"
        "Path(os.environ['OUROBOROS_DATA_DIR'])); print(json.dumps(list(r._entries)))"
    )
    names = json.loads(
        subprocess.check_output(
            [str(python), "-c", registry_code],
            env=isolated_env(root, repo),
            cwd=repo,
            text=True,
            timeout=30,
        )
    )
    allowed = {"finish_task", "list_available_tools", "enable_tools", "list_skills"}
    disabled = sorted(set(names) - allowed)
    return client.post(
        "/api/tasks",
        json={
            "description": prompt,
            "title": "OilAgent bounded integration",
            "execution_timeout_sec": 300,
            "disabled_tools": disabled,
            "actor_id": "cli",
            "source": "cli",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["prepare", "serve", "catalog", "install", "review", "enable", "skill", "run"],
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--prompt-file")
    args = parser.parse_args()
    if args.action == "prepare":
        root, _, _ = prepare()
        print(f"Isolated runtime prepared: {root}; no model requests were made.")
        return
    root, python = runtime_paths()
    repo = root / "repo"
    if not (root / "data/settings.json").exists():
        parser.error("Run prepare first")
    if args.action == "serve":
        subprocess.run(
            [
                str(python),
                str(Path(__file__).with_name("native_ouroboros.py")),
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            env=isolated_env(root, repo),
            cwd=repo,
            check=True,
        )
        return
    with httpx.Client(
        base_url=f"http://127.0.0.1:{args.port}", trust_env=False, timeout=30
    ) as client:
        if args.action == "catalog":
            result = client.get("/api/skill-catalog/search", params={"source": "oilagent"})
        elif args.action == "install":
            # Local sources are read in place; the installer returns 409 for them.
            result = client.post(
                "/api/skill-catalog/install",
                json={"id": "oilagent/oilgas_analyst", "turn_on_when_ready": True},
            )
            if result.status_code == 409 and result.json().get("code") == "local_source":
                print({"status": "registered_in_place", "review_required": True})
                return
        elif args.action in {"review", "enable"}:
            rows = client.get("/api/extensions").json()["skills"]
            skill = next(row for row in rows if row["name"] == "oilgas_analyst")
            reviewed = skill.get("executable_review") and not skill.get("review_stale")
            if args.action == "review" and reviewed:
                print({"status": "reused_exact_review", "content_hash": skill["content_hash"]})
                return
            if args.action == "enable" and not reviewed:
                parser.error("Skill has no current executable review; no bypass is permitted")
            result = client.post(
                "/api/skills/oilgas_analyst/review"
                if args.action == "review"
                else "/api/skills/oilgas_analyst/toggle",
                json={}
                if args.action == "review"
                else {"enabled": True, "expected_content_hash": skill["content_hash"]},
            )
        elif args.action == "skill":
            result = client.get("/api/extensions")
        else:
            if not args.prompt_file:
                parser.error("run requires --prompt-file")
            try:
                result = submit_task(client, args.prompt_file)
            except ValueError as exc:
                parser.error(str(exc))

        result.raise_for_status()
        data = result.json()
        if args.action == "skill":
            rows = data.get("skills", data.get("extensions", []))
            data = [
                {
                    k: row.get(k)
                    for k in [
                        "name",
                        "enabled",
                        "review_status",
                        "review_stale",
                        "executable_review",
                        "content_hash",
                    ]
                }
                for row in rows
                if row.get("name") == "oilgas_analyst"
            ]
        elif args.action == "catalog":
            data = [{"id": row.get("id"), "name": row.get("name")} for row in data.get("items", [])]
        else:
            data = {
                k: data[k]
                for k in [
                    "ok",
                    "task_id",
                    "status",
                    "job_id",
                    "enabled",
                    "review_status",
                    "executable_review",
                ]
                if k in data
            }
        print(data)


if __name__ == "__main__":
    main()
