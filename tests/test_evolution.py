import subprocess

import pytest
from pydantic import ValidationError

from analyst.contracts import RetrievalPolicy
from analyst.evolution import ARTIFACT, SEED, SKILL_ARTIFACT, Evolution
from analyst.graph import answer_question


@pytest.fixture
def backend(tmp_path):
    backend = Evolution(tmp_path)
    # Synthetic gate tests use a deliberately incomplete fixture, never serving defaults.
    path = backend.repo / ARTIFACT
    path.write_text(RetrievalPolicy().model_dump_json())
    backend.git("add", ARTIFACT)
    backend.git("commit", "-m", "Set synthetic pooled fixture")
    return backend


def propose(backend, policy=None, key="test-1", artifact=ARTIFACT):
    return backend.propose(
        backend.baseline()["base_sha"],
        artifact,
        policy or RetrievalPolicy(comparison_strategy="per_publisher"),
        "Restore publisher coverage",
        "fixture-failure-1",
        key,
    )


def test_candidate_commit_does_not_change_baseline(backend):
    base = backend.baseline()["base_sha"]
    candidate = propose(backend)
    assert candidate["candidate_sha"] != base
    assert backend.baseline()["base_sha"] == base
    assert backend.git("show", f"{base}:{ARTIFACT}") != backend.git(
        "show", f"{candidate['candidate_sha']}:{ARTIFACT}"
    )
    diff = backend.diff(candidate["candidate_id"])
    assert "per_publisher" in diff["diff"]
    assert len(diff["diff_sha256"]) == 64


def test_explicit_sibling_repo_keeps_runtime_state_outside_git(tmp_path):
    core = tmp_path / "core"
    core.mkdir()
    sentinel = core / "developer.py"
    sentinel.write_text("# developer owned\n")
    repo = tmp_path / "evolution"
    backend = Evolution(core / "workspace", repo=repo)
    state = propose(backend)
    assert backend.git("rev-parse", "--show-toplevel") == str(repo)
    assert backend.load(state["candidate_id"]) == state
    assert (core / "workspace/candidates" / f"{state['candidate_id']}.json").exists()
    assert not (repo / "candidates").exists()
    assert sentinel.read_text() == "# developer owned\n"


@pytest.mark.parametrize("initial", ["missing", "directory", "unborn_main", "unborn_master"])
def test_first_start_seeds_empty_evolution_and_is_repeatable(tmp_path, initial):
    repo = tmp_path / "evolution"
    if initial != "missing":
        repo.mkdir()
    if initial.startswith("unborn_"):
        branch = initial.removeprefix("unborn_")
        subprocess.run(
            ["git", "-C", str(repo), "init", f"--initial-branch={branch}"],
            check=True,
            capture_output=True,
        )
    first = Evolution(tmp_path / "runtime", repo=repo)
    baseline = first.baseline()
    assert baseline["policy"] == SEED
    assert first.git("show", f"{baseline['base_sha']}:{SKILL_ARTIFACT}")
    assert not first.git("status", "--porcelain")
    assert not baseline["release_available"]
    assert Evolution(tmp_path / "runtime", repo=repo).baseline() == baseline
    assert first.git("rev-list", "--count", "main") == "1"


def test_existing_baseline_policy_is_read_from_git_not_reset(backend):
    policy = RetrievalPolicy(comparison_strategy="per_publisher", top_k_per_publisher=3)
    (backend.repo / ARTIFACT).write_text(policy.model_dump_json())
    backend.git("add", ARTIFACT)
    backend.git("commit", "-m", "Existing operator policy")
    sha = backend.git("rev-parse", "main")
    restarted = Evolution(backend.root, repo=backend.repo)
    assert restarted.baseline()["base_sha"] == sha
    assert restarted.baseline()["policy"] == policy.model_dump()
    assert not backend.git("status", "--porcelain")


def test_existing_history_without_required_policy_is_not_overwritten(backend):
    backend.git("rm", ARTIFACT)
    backend.git("commit", "-m", "Existing history without policy")
    sha = backend.git("rev-parse", "main")
    with pytest.raises(ValueError, match="must contain main"):
        Evolution(backend.root, repo=backend.repo)
    assert backend.git("rev-parse", "main") == sha
    assert not (backend.repo / ARTIFACT).exists()


def test_uncommitted_policy_is_not_overwritten(tmp_path):
    repo = tmp_path / "evolution"
    (repo / ARTIFACT).parent.mkdir(parents=True)
    (repo / ARTIFACT).write_text("operator-owned unfinished policy")
    with pytest.raises(ValueError, match="Uncommitted"):
        Evolution(tmp_path / "runtime", repo=repo)
    assert (repo / ARTIFACT).read_text() == "operator-owned unfinished policy"


def test_idempotency_and_conflict_survive_restart(backend):
    first = propose(backend)
    restarted = Evolution(backend.root)
    assert propose(restarted) == first
    with pytest.raises(ValueError, match="conflicts"):
        propose(restarted, RetrievalPolicy(), key="test-1")


@pytest.mark.parametrize("artifact", ["../core.py", "evals/gold.json", "/tmp/x", "policies/x"])
def test_protected_paths_rejected(backend, artifact):
    with pytest.raises(ValueError, match="Only"):
        propose(backend, artifact=artifact)


@pytest.mark.parametrize(
    "payload",
    [
        {"allow_unverified_sources": True},
        {"top_k_per_publisher": 100},
        {"top_k_per_publisher": "3"},
        {"comparison_strategy": "exec"},
    ],
)
def test_policy_schema_rejects_expansion(payload):
    with pytest.raises(ValidationError):
        RetrievalPolicy.model_validate(payload)


def test_real_policy_branch_changes_fixture_coverage(backend):
    state = propose(backend)
    result = backend.checks(state["candidate_id"])
    assert result["checks"]["fixture_coverage_before"] == 0.5
    assert result["checks"]["fixture_coverage_after"] == 1.0
    assert result["status"] == "CHECKS_PASSED"
    assert not result["release_available"]


def test_no_improvement_is_rejected(backend):
    state = propose(backend, RetrievalPolicy())
    result = backend.checks(state["candidate_id"])
    assert result["status"] == "REJECTED"
    with pytest.raises(ValueError, match="Checks"):
        backend.review(state["candidate_id"])


def test_missing_critic_fails_closed(backend, monkeypatch):
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    state = propose(backend)
    backend.checks(state["candidate_id"])
    reviewed = backend.review(state["candidate_id"])
    assert reviewed["status"] == "REVIEW_BLOCKED"
    assert "critic" not in reviewed
    assert not reviewed["release_available"]


def test_candidate_id_cannot_escape_store(backend):
    with pytest.raises(ValueError, match="ID"):
        backend.load("../../core")


def test_graph_without_model_does_not_fabricate_answer(monkeypatch):
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    result = answer_question("Каков прогноз Brent?")
    assert result["status"] == "insufficient_evidence"
    assert result["route"] is None
    assert result["warnings"] == ["llm_not_configured"]
    assert result["request_id"]
