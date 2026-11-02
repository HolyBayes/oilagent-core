"""Fresh application storage/bootstrap probe; build layers may be cached. No LLM calls."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="oilagent-cold-", dir="/tmp"))
checkout = root / "core"
checkout.mkdir()
for name in subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0"):
    source = Path(name)
    if name and source.is_file():
        target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        shutil.copymode(source, target)
env = {
    **os.environ,
    "COMPOSE_PROJECT_NAME": "oilagent-cold-audit",
    "DEPLOY_WORKSPACE": str(root / "deploy"),
    "USER_FILES_PATH": str(root / "files"),
    "EVOLUTION_REPO_PATH": str(root / "evolution"),
    "RUNNER_PORT": "18813",
}
report = {
    "storage": str(root),
    "empty_application_data": True,
    "cached_build_layers_allowed": True,
    "llm_calls": 0,
    "bootstrap_passed": False,
}
log = Path("workspace/cold-start.log")
try:
    with log.open("w") as output:
        subprocess.run(
            ["./run.sh", "-d", "init"],
            env=env,
            cwd=checkout,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=180,
        )
        result = subprocess.run(
            ["./compose.sh", "wait", "init"],
            env=env,
            cwd=checkout,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=180,
        )
        report["bootstrap_passed"] = result.returncode == 0
        report["exit_code"] = result.returncode
        subprocess.run(
            ["./compose.sh", "logs", "--tail", "35", "init"],
            env=env,
            cwd=checkout,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
except (subprocess.SubprocessError, OSError) as exc:
    report["error_type"] = type(exc).__name__
finally:
    subprocess.run(["./compose.sh", "down"], env=env, cwd=checkout, capture_output=True, timeout=30)
    Path("docs/cold-start-evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
