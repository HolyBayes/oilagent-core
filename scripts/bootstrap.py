"""Fetch the exact upstream snapshot and prepare a private .env; no model calls."""

import json
import secrets
import subprocess
from pathlib import Path

from analyst.config import configured_path, evolution_repo, workspace
from analyst.evolution import Evolution

ROOT = Path(__file__).resolve().parents[1]


def main():
    pin = json.loads((ROOT / "config/ouroboros-pin.json").read_text())
    checkout = configured_path("OUROBOROS_PATH", "../workspace/upstream/ouroboros")
    if not checkout.exists():
        checkout.mkdir(parents=True)
        commands = [
            ["init"],
            ["remote", "add", "origin", pin["repository"]],
            ["fetch", "--depth", "1", "origin", pin["commit"]],
            ["checkout", "--detach", "FETCH_HEAD"],
        ]
        for command in commands:
            subprocess.run(["git", "-C", str(checkout), *command], check=True, timeout=120)
    actual = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != pin["commit"]:
        raise RuntimeError("Existing checkout differs from pin; inspect it before replacing")
    path = ROOT / ".env"
    if not path.exists():
        text = (ROOT / ".env.example").read_text()
        for kind in ["ANALYST", "EVOLUTION"]:
            text = text.replace(
                f"{kind}_MCP_TOKEN=\n", f"{kind}_MCP_TOKEN={secrets.token_urlsafe(32)}\n"
            )
        with path.open("x") as handle:
            handle.write(text)
        path.chmod(0o600)
    backend = Evolution(workspace(), repo=evolution_repo())
    print(f"Independent Evolution Git: {backend.repo}")
    print(f"Pinned Ouroboros {actual}; existing .env preserved; secret values not printed.")


if __name__ == "__main__":
    main()
