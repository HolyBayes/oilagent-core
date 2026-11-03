import json
import subprocess
from pathlib import Path

import pytest

from analyst.config import CORE_ROOT


def test_recursive_clone_git_mounts(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CORE_ROOT))
    from scripts.prepare_submodules import prepare

    # A real submodule-style reference, no network or credential use.
    repo = tmp_path / "evolution"
    repo.mkdir()
    directory = tmp_path / ".git/modules/evolution"
    directory.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--separate-git-dir", str(directory), str(repo)],
        check=True,
        capture_output=True,
    )
    (repo / ".git").write_text("gitdir: ../.git/modules/evolution\n")
    output = tmp_path / "override.json"
    prepare(repo, output)
    services = json.loads(output.read_text())["services"]
    assert set(services) == {"init", "evolution", "analyst", "ouroboros"}
    for name, service in services.items():
        mount = service["volumes"][0]
        assert Path(mount["source"]) == directory
        assert mount["target"] == "/.git/modules/evolution"
        assert mount["read_only"] == (name in {"analyst", "ouroboros"})
    assert (repo / ".git").is_file()


def test_standalone_checkout_removes_stale_override(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CORE_ROOT))
    from scripts.prepare_submodules import prepare

    output = tmp_path / "override.json"
    output.write_text("{}")
    prepare(tmp_path / "empty-evolution", output)
    assert json.loads(output.read_text()) == {"services": {}}


def test_unexpected_git_reference_is_rejected(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CORE_ROOT))
    from scripts.prepare_submodules import prepare

    (tmp_path / ".git").write_text("gitdir: /etc\n")
    with pytest.raises(ValueError, match="Unsupported"):
        prepare(tmp_path, tmp_path / "out.json")
