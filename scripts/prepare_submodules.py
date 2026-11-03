"""Expose an external submodule Git directory at its referenced container path."""

import json
import os
import posixpath
import subprocess
from pathlib import Path


def prepare(repo, output):
    repo, output = Path(repo).resolve(), Path(output)
    services = {}
    marker = repo / ".git"
    if marker.is_file():
        prefix, reference = marker.read_text().strip().split(":", 1)
        if prefix != "gitdir":
            raise ValueError("Invalid evolution .git reference")
        reference = reference.strip()
        target = posixpath.normpath(posixpath.join("/evolution", reference))
        # Support standard recursive clones without exposing arbitrary container paths.
        if target != "/.git/modules/evolution":
            raise ValueError(
                "Unsupported evolution Git layout; clone a standalone evolution checkout"
            )
        directory = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"], text=True
        ).strip()
        for name in ["init", "analyst", "evolution", "ouroboros"]:
            services[name] = {
                "volumes": [
                    {
                        "type": "bind",
                        "source": directory,
                        "target": target,
                        "read_only": name in {"analyst", "ouroboros"},
                    }
                ]
            }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"services": services}, indent=2) + "\n")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
    prepare(os.getenv("EVOLUTION_REPO_PATH") or "../evolution", "workspace/submodules.compose.json")
