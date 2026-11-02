"""Operator-only releases. The agent MCP never exposes these mutations."""

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

from analyst.config import CORE_ROOT, configured_path
from analyst.contracts import RetrievalPolicy

SCHEMA_VERSION = 1


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity():
    files = sorted(
        [
            *(CORE_ROOT / "src/analyst").rglob("*.py"),
            *(CORE_ROOT / "scripts").glob("native_*.py"),
            CORE_ROOT / "scripts/container_native.py",
        ]
    )
    code = sha(b"".join(str(p.relative_to(CORE_ROOT)).encode() + p.read_bytes() for p in files))
    corpus = sha((CORE_ROOT / "data/reports.json").read_bytes())
    return {
        "core_source_sha256": code,
        "capability_policy_sha256": sha((CORE_ROOT / "config/capabilities.json").read_bytes()),
        "corpus_manifest_sha256": corpus,
        "embedding_config_sha256": sha((CORE_ROOT / "config/embedding.json").read_bytes()),
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode()


def release_directory():
    return configured_path("RELEASE_PATH", "workspace/releases")


def validate_bundle(bundle):
    if bundle["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported release schema")
    if bundle["identity"] != identity():
        raise ValueError("Release belongs to different code or corpus; evaluate again")
    RetrievalPolicy.model_validate(bundle["policy"])
    return bundle


def read_bundle(release_id):
    if not re.fullmatch("[0-9a-f]{64}", release_id):
        raise ValueError("Invalid release ID")
    data = (release_directory() / "bundles" / f"{release_id}.json").read_bytes()
    if sha(data) != release_id:
        raise ValueError("Release bundle hash mismatch")
    return validate_bundle(json.loads(data))


def active_release():
    pointer = release_directory() / "active.json"
    if not pointer.exists():
        # Match the existing production retrieval behavior; do not degrade a baseline
        # merely to manufacture an apparent evolution improvement.
        return {
            "release_id": "developer-seed",
            "policy": {"comparison_strategy": "per_publisher", "top_k_per_publisher": 4},
            "identity": identity(),
        }
    release_id = json.loads(pointer.read_text())["release_id"]
    return {"release_id": release_id, **read_bundle(release_id)}


def activate(release_id):
    if release_id == "developer-seed":
        (release_directory() / "active.json").unlink(missing_ok=True)
        return
    read_bundle(release_id)
    root = release_directory()
    root.mkdir(parents=True, exist_ok=True)
    temp = root / "active.tmp"
    temp.write_text(json.dumps({"release_id": release_id}) + "\n")
    temp.replace(root / "active.json")


def publish(backend, candidate_id, expected_sha, approved_by):
    import fcntl

    root = release_directory()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "release.lock").open("a") as lock, backend.lock():
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = backend.load(candidate_id)
        if state["candidate_sha"] != expected_sha or not approved_by.strip():
            raise ValueError("Approval must name the exact candidate SHA and operator")
        existing = state.get("release_id")
        if existing:
            read_bundle(existing)
            return existing
        intent = root / f"approval-{candidate_id}.json"
        if intent.exists():
            pending = json.loads(intent.read_text())
            bundle = read_bundle(pending["release_id"])
            if bundle["candidate_sha"] != expected_sha or bundle["approved_by"] != approved_by:
                raise ValueError("Approval intent conflicts with operator arguments")
            # Reconcile an interruption between pointer activation and state persistence.
            if active_release()["release_id"] not in {pending["previous"], pending["release_id"]}:
                raise ValueError("Another release superseded this interrupted approval")
            activate(pending["release_id"])
            state.update(status="RELEASED", release_id=pending["release_id"])
            backend.save(state)
            return pending["release_id"]
        checks = state.get("quality_checks", {})
        critic = state.get("critic", {})
        if not checks.get("passed") or critic.get("verdict") != "APPROVE":
            raise ValueError("Real quality checks and APPROVE critic are required")
        from analyst.evolution import fingerprint

        if (
            critic.get("candidate_sha") != expected_sha
            or checks["identity"] != identity()
            or critic.get("checks_sha256") != fingerprint(checks)
        ):
            raise ValueError("Review/checks are stale")
        if checks["active_release_id"] != active_release()["release_id"]:
            raise ValueError("Serving baseline changed; evaluate again")
        current_eval = configured_path("EVOLUTION_EVAL_PATH", "data/evolution_eval.json")
        if checks["eval_sha256"] != sha(current_eval.read_bytes()):
            raise ValueError("Evaluation dataset changed since checks")
        paths = backend.git("diff", "--name-only", state["base_sha"], expected_sha)
        if paths != "policies/retrieval.json":
            raise ValueError("Protected artifacts changed")
        policy = RetrievalPolicy.model_validate_json(
            backend.git("show", f"{expected_sha}:policies/retrieval.json")
        ).model_dump()
        current_policy = active_release()["policy"]
        if checks["baseline_policy"] != current_policy or checks["candidate_policy"] != policy:
            raise ValueError("Evaluated policy mismatch")
        bundle = {
            "schema_version": SCHEMA_VERSION,
            "identity": identity(),
            "policy": policy,
            "candidate_sha": expected_sha,
            "baseline_sha": state["base_sha"],
            "core_sha": subprocess.check_output(
                ["git", "-C", str(CORE_ROOT), "rev-parse", "HEAD"], text=True
            ).strip(),
            "checks_sha256": sha(canonical(checks)),
            "critic_sha256": sha(canonical(critic)),
            "eval_sha256": checks["eval_sha256"],
            "model": checks["model"],
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
        data = canonical(bundle)
        release_id = sha(data)
        (root / "bundles").mkdir(exist_ok=True)
        target = root / "bundles" / f"{release_id}.json"
        if not target.exists():
            target.write_bytes(data)
            target.chmod(0o444)
        intent.write_text(
            json.dumps({"release_id": release_id, "previous": active_release()["release_id"]})
        )
        activate(release_id)
        state.update(status="RELEASED", release_id=release_id)
        backend.save(state)
        return release_id


def rollback(release_id):
    import fcntl

    root = release_directory()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "release.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        activate(release_id)
    return release_id
