import json

import pytest

from analyst.config import CORE_ROOT
from analyst.contracts import RetrievalPolicy
from analyst.evolution import ARTIFACT, Evolution, fingerprint
from analyst.releases import active_release, identity, publish, read_bundle, rollback, sha


@pytest.fixture
def reviewed(tmp_path, monkeypatch):
    monkeypatch.setenv("RELEASE_PATH", str(tmp_path / "releases"))
    backend = Evolution(tmp_path / "runtime")
    policy = RetrievalPolicy(comparison_strategy="per_publisher", top_k_per_publisher=3)
    state = backend.propose(
        backend.baseline()["base_sha"],
        ARTIFACT,
        policy,
        "Fixture candidate",
        "fixture-request",
        "fixture-approval",
    )
    checks = {
        "passed": True,
        "identity": identity(),
        "active_release_id": "developer-seed",
        "baseline_policy": active_release()["policy"],
        "candidate_policy": policy.model_dump(),
        "eval_sha256": sha((CORE_ROOT / "data/evolution_eval.json").read_bytes()),
        "model": {"model": "fixture"},
    }
    state["quality_checks"] = checks
    state["critic"] = {
        "verdict": "APPROVE",
        "candidate_sha": state["candidate_sha"],
        "checks_sha256": fingerprint(checks),
    }
    backend.save(state)
    return backend, state


def test_operator_release_activation_and_rollback(reviewed):
    backend, state = reviewed
    release_id = publish(backend, state["candidate_id"], state["candidate_sha"], "test operator")
    assert active_release()["release_id"] == release_id
    assert active_release()["policy"]["top_k_per_publisher"] == 3
    assert (
        publish(backend, state["candidate_id"], state["candidate_sha"], "test operator")
        == release_id
    )
    assert rollback("developer-seed") == "developer-seed"
    assert active_release()["policy"]["top_k_per_publisher"] == 4
    rollback(release_id)
    assert read_bundle(release_id)["candidate_sha"] == state["candidate_sha"]


@pytest.mark.parametrize("fault", ["sha", "critic", "checks", "binding", "baseline", "protected"])
def test_release_rejects_stale_or_unapproved_tuple(reviewed, fault):
    backend, state = reviewed
    if fault == "critic":
        state["critic"]["verdict"] = "REJECT"
    if fault == "checks":
        state["quality_checks"]["passed"] = False
    if fault == "binding":
        state["critic"]["checks_sha256"] = "wrong"
    if fault == "baseline":
        state["quality_checks"]["baseline_policy"] = {}
    if fault == "protected":
        state["candidate_sha"] = "b" * 40
    backend.save(state)
    requested = "c" * 40 if fault == "sha" else state["candidate_sha"]
    with pytest.raises((ValueError, KeyError)):
        publish(backend, state["candidate_id"], requested, "test operator")
    assert active_release()["release_id"] == "developer-seed"


def test_modified_bundle_is_rejected(reviewed, monkeypatch, tmp_path):
    backend, state = reviewed
    rid = publish(backend, state["candidate_id"], state["candidate_sha"], "test operator")
    path = tmp_path / "releases/bundles" / f"{rid}.json"
    path.chmod(0o600)
    content = json.loads(path.read_text())
    content["policy"]["top_k_per_publisher"] = 2
    path.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="hash"):
        read_bundle(rid)


def test_interrupted_release_reconciles_before_retry(reviewed, monkeypatch):
    backend, state = reviewed
    save = backend.save

    def crash(value):
        if value.get("status") == "RELEASED":
            raise OSError("simulated interrupted state write")
        return save(value)

    monkeypatch.setattr(backend, "save", crash)
    with pytest.raises(OSError):
        publish(backend, state["candidate_id"], state["candidate_sha"], "test operator")
    rid = active_release()["release_id"]
    monkeypatch.setattr(backend, "save", save)
    assert publish(backend, state["candidate_id"], state["candidate_sha"], "test operator") == rid
