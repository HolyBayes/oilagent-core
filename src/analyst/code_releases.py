"""Whole-package staging. Python is active only after native review of the same bytes."""

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone

from analyst.code_evaluation import active_id, evaluation_identity
from analyst.code_packages import SLOTS, artifact, repository_files, seed_source, validate_source
from analyst.evolution import atomic_json, fingerprint
from analyst.method_runtime import code_root
from analyst.releases import canonical, sha
from analyst.skill_release import native_skill


def package_hash(files, name):
    digest = hashlib.sha256(b"ouroboros-skill-release/2\0")
    prefix = f"ouroboros_skills/{name}/"
    for path in sorted(files):
        if path.startswith(prefix):
            digest.update(path[len(prefix) :].encode() + b"\0")
            digest.update(bytes.fromhex(sha(files[path].encode())))
    return digest.hexdigest()


def validate_files(files):
    from analyst.skill_evolution import validate_skill

    for path, source in files.items():
        if path.endswith("/SKILL.md"):
            validate_skill(path, source)
        elif path in {artifact(slot) for slot in SLOTS}:
            slot = next(slot for slot in SLOTS if artifact(slot) == path)
            validate_source(slot, source)
        else:
            raise ValueError("Unexpected executable package artifact")
    for slot in SLOTS:
        validate_source(slot, files[artifact(slot)])


def read_bundle(release_id, *, historical=False):
    if not re.fullmatch("[0-9a-f]{64}", release_id):
        raise ValueError("Invalid code release ID")
    raw = (code_root() / "bundles" / f"{release_id}.json").read_bytes()
    if sha(raw) != release_id:
        raise ValueError("Code release integrity mismatch")
    bundle = json.loads(raw)
    if not historical and bundle["identity"] != evaluation_identity():
        raise ValueError("Code/executor/data changed; evaluate and release again")
    validate_files(bundle["files"])
    return {"release_id": release_id, **bundle}


@contextmanager
def release_lock():
    import fcntl

    root = code_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "release.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def freeze(files, metadata):
    if (code_root() / "prepared.json").exists():
        raise ValueError("A package is already staged; enable or abort it first")
    validate_files(files)
    bundle = {
        **metadata,
        "files": files,
        "identity": evaluation_identity(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = canonical(bundle)
    release_id = sha(raw)
    root = code_root()
    (root / "bundles").mkdir(parents=True, exist_ok=True)
    path = root / "bundles" / f"{release_id}.json"
    if not path.exists():
        path.write_bytes(raw)
        path.chmod(0o444)
    target = root / "packages" / release_id
    if not target.exists():
        temp = root / "packages" / ("staging-" + release_id)
        temp.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            destination = temp / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
            destination.chmod(0o444)
        temp.rename(target)
    atomic_json(root / "maintenance.json", {"release_id": release_id})
    atomic_json(root / "prepared.json", {"release_id": release_id})
    return release_id


def seed(backend, operator):
    if not operator.strip():
        raise ValueError("Operator required")
    with release_lock(), backend.lock():
        if (code_root() / "active.json").exists():
            raise ValueError("Developer seed cannot overwrite an active release")
        if (
            backend.git("status", "--porcelain")
            or backend.git("symbolic-ref", "--short", "HEAD") != "main"
        ):
            raise ValueError("Clean evolution main required")
        for slot in SLOTS:
            path = backend.repo / artifact(slot)
            if path.exists() and path.read_text() != seed_source(slot):
                raise ValueError("Existing Python differs from the developer seed")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(seed_source(slot))
        backend.git("add", "--", *[artifact(slot) for slot in SLOTS])
        if backend.git("diff", "--cached", "--name-only"):
            backend.git(
                "commit", "-m", "Seed executable skill methods from verified developer baseline"
            )
        commit = backend.baseline()["base_sha"]
        return freeze(
            repository_files(backend, commit),
            {
                "kind": "developer-seed",
                "source_commit": commit,
                "approved_by": operator,
                "previous_release_id": "developer-seed",
            },
        )


def verified_state(backend, candidate_id, expected_sha):
    state = backend.load(candidate_id)
    checks = state.get("quality_checks", {})
    critic = state.get("critic", {})
    files = repository_files(backend, expected_sha)
    if state.get("skill_name") and not state.get("code_slot"):
        from analyst.skill_release import verified_candidate

        verified_candidate(backend, state, expected_sha, "package-stage")
        if active_id() not in {checks.get("active_release_id"), state.get("code_release_id")}:
            raise ValueError("Serving package changed; evaluate instructions again")
        return state, files
    if (
        state["candidate_sha"] != expected_sha
        or not checks.get("passed")
        or checks.get("identity") != evaluation_identity()
        or checks.get("candidate_sha") != expected_sha
        or active_id() not in {checks.get("active_release_id"), state.get("code_release_id")}
        or critic.get("candidate_sha") != expected_sha
        or critic.get("verdict") != "APPROVE"
        or critic.get("checks_sha256") != fingerprint(checks)
    ):
        raise ValueError("Fresh paired checks and exact critic approval required")
    if checks["package_sha256"] != sha(json.dumps(files, sort_keys=True).encode()):
        raise ValueError("Evaluated package differs")
    return state, files


def stage(backend, candidate_id, expected_sha, operator):
    if not operator.strip():
        raise ValueError("Operator required")
    with release_lock(), backend.lock():
        state, files = verified_state(backend, candidate_id, expected_sha)
        if state.get("code_release_id") and (code_root() / "prepared.json").exists():
            prepared = json.loads((code_root() / "prepared.json").read_text())["release_id"]
            if prepared != state["code_release_id"]:
                raise ValueError("A different package is already staged")
            return state["code_release_id"]
        if backend.git("status", "--porcelain"):
            raise ValueError("Evolution worktree must be clean")
        if backend.baseline()["base_sha"] != state["base_sha"]:
            raise ValueError("Evolution baseline changed")
        release_id = freeze(
            files,
            {
                "kind": "evolved",
                "source_commit": expected_sha,
                "candidate_id": candidate_id,
                "previous_release_id": active_id(),
                "checks_sha256": fingerprint(state["quality_checks"]),
                "critic_sha256": fingerprint(state["critic"]),
                "approved_by": operator,
            },
        )
        state.update(status="STAGED_FOR_NATIVE_REVIEW", code_release_id=release_id)
        backend.save(state)
        return release_id


def review(client, release_id):
    bundle = read_bundle(release_id)
    result = {}
    for name in sorted({p.split("/")[1] for p in bundle["files"] if p.endswith("/SKILL.md")}):
        skill = native_skill(client, name)
        if not skill or skill["content_hash"] != package_hash(bundle["files"], name):
            raise ValueError("Restart native runtime on the staged package first: " + name)
        if skill.get("executable_review") and not skill.get("review_stale"):
            result[name] = "reused_exact_review"
            continue
        response = client.post(f"/api/skills/{name}/review", json={})
        response.raise_for_status()
        result[name] = response.json()
    return result


def enable(backend, client, release_id, operator):
    if not operator.strip():
        raise ValueError("Operator required")
    with release_lock(), backend.lock():
        bundle = read_bundle(release_id)
        prepared = json.loads((code_root() / "prepared.json").read_text())["release_id"]
        if prepared != release_id:
            raise ValueError("Stage and restart native runtime first")
        if bundle["kind"] == "evolved":
            state, _ = verified_state(backend, bundle["candidate_id"], bundle["source_commit"])
        names = [path.split("/")[1] for path in bundle["files"] if path.endswith("/SKILL.md")]
        for name in names:
            skill = native_skill(client, name)
            if (
                not skill
                or skill["content_hash"] != package_hash(bundle["files"], name)
                or not skill.get("executable_review")
                or skill.get("review_stale")
            ):
                raise ValueError("Native exact-package review required: " + name)
        # Content activation never changes the owner's native skill switches.
        if (
            bundle["kind"] == "evolved"
            and backend.baseline()["base_sha"] != bundle["source_commit"]
        ):
            if backend.git("status", "--porcelain"):
                raise ValueError("Evolution worktree changed")
            backend.git("merge", "--ff-only", bundle["source_commit"])
        elif bundle["kind"] == "rollback":
            restore_main(backend, bundle["files"])
        atomic_json(code_root() / "active.json", {"release_id": release_id})
        (code_root() / "prepared.json").unlink(missing_ok=True)
        (code_root() / "maintenance.json").unlink(missing_ok=True)
        if bundle["kind"] == "evolved":
            state.update(status="CODE_RELEASED", code_release_id=release_id)
            backend.save(state)
        return release_id


def restore_main(backend, files):
    if (
        backend.git("status", "--porcelain")
        or backend.git("symbolic-ref", "--short", "HEAD") != "main"
    ):
        raise ValueError("Clean evolution main required")
    current = repository_files(backend, backend.baseline()["base_sha"])
    for name in current.keys() - files.keys():
        (backend.repo / name).unlink()
    for name, content in files.items():
        path = backend.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    backend.git("add", "--", "ouroboros_skills")
    if backend.git("diff", "--cached", "--name-only"):
        backend.git("commit", "-m", "Restore previously reviewed executable skill package")


def prepare_rollback(release_id, operator):
    if not operator.strip():
        raise ValueError("Operator required")
    with release_lock():
        bundle = read_bundle(release_id)
        return freeze(
            bundle["files"],
            {
                "kind": "rollback",
                "source_commit": bundle["source_commit"],
                "previous_release_id": active_id(),
                "approved_by": operator,
            },
        )


def abort(release_id, operator):
    if not operator.strip():
        raise ValueError("Operator required")
    with release_lock():
        path = code_root() / "prepared.json"
        if json.loads(path.read_text())["release_id"] != release_id:
            raise ValueError("Different staged package")
        previous = active_id()
        if previous == "developer-seed":
            raise ValueError("Initial seed must complete review before admission opens")
        read_bundle(previous)
        # Keep admission closed; restart native on this source, then enable it.
        atomic_json(path, {"release_id": previous})
        return previous
