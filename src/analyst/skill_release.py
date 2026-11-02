"""Operator staging and hash-bound native review/enable for instruction candidates."""

import hashlib

from analyst.evolution import fingerprint
from analyst.skill_evolution import (
    evaluation_identity,
    validate_skill,
    validate_skill_tree,
)


def content_hash(backend, state):
    from analyst.code_packages import repository_files
    from analyst.code_releases import package_hash

    return package_hash(repository_files(backend, state["candidate_sha"]), state["skill_name"])


def native_skill(client, name):
    response = client.get("/api/extensions")
    response.raise_for_status()
    return next((s for s in response.json()["skills"] if s["name"] == name), None)


def toggle(client, skill, enabled):
    response = client.post(
        f"/api/skills/{skill['name']}/toggle",
        json={"enabled": enabled, "expected_content_hash": skill["content_hash"]},
    )
    response.raise_for_status()
    if response.json().get("enabled") != enabled:
        raise ValueError("Native skill toggle did not complete")


def verified_candidate(backend, state, expected_sha, operator):
    if not operator.strip() or state["candidate_sha"] != expected_sha:
        raise ValueError("Operator and exact candidate SHA are required")
    checks, critic = state.get("quality_checks", {}), state.get("critic", {})
    if (
        not checks.get("passed")
        or checks.get("identity") != evaluation_identity()
        or checks.get("candidate_sha") != expected_sha
        or critic.get("verdict") != "APPROVE"
        or critic.get("candidate_sha") != expected_sha
        or critic.get("checks_sha256") != fingerprint(checks)
    ):
        raise ValueError("Current skill evaluation and hash-bound APPROVE critic are required")
    paths = backend.git("diff", "--name-only", state["base_sha"], expected_sha)
    if paths != state["artifact"] or not state.get("skill_name"):
        raise ValueError("Only the evaluated instruction artifact may change")
    content = backend.git("show", f"{expected_sha}:{state['artifact']}", raw=True)
    validate_skill(state["artifact"], content)
    validate_skill_tree(backend, state)
    if hashlib.sha256(content.encode()).hexdigest() != state["content_sha256"]:
        raise ValueError("Candidate content hash mismatch")
    return content


def stage(backend, client, candidate_id, expected_sha, operator):
    from analyst.method_runtime import code_root

    if (code_root() / "active.json").exists():
        from analyst.code_releases import stage as stage_package

        stage_package(backend, candidate_id, expected_sha, operator)
        return backend.load(candidate_id)
    with backend.lock():
        state = backend.load(candidate_id)
        content = verified_candidate(backend, state, expected_sha, operator)
        if backend.git("status", "--porcelain"):
            raise ValueError("Evolution worktree must be clean before staging")
        head = backend.git("rev-parse", "HEAD")
        if backend.git("symbolic-ref", "--short", "HEAD") != "main":
            raise ValueError("Evolution must be on main")
        if head not in {state["base_sha"], expected_sha}:
            raise ValueError("Evolution baseline changed; evaluate again")
        installed = native_skill(client, state["skill_name"])
        if installed and installed.get("enabled"):
            toggle(client, installed, False)
        if head != expected_sha:
            backend.git("merge", "--ff-only", expected_sha)
        installed = native_skill(client, state["skill_name"])
        if installed is None:
            raise ValueError("Native source has not discovered the staged skill; retry stage")
        if installed["content_hash"] != content_hash(backend, state):
            raise ValueError("UI belongs to a different skill payload/installation")
        # /api/extensions discovers the local source in place. The native content
        # hash covers its payload, distinct from SHA256 of SKILL.md alone.
        if (backend.repo / state["artifact"]).read_text() != content:
            raise ValueError("Staged bytes differ from the candidate")
        state.update(
            status="STAGED_FOR_NATIVE_REVIEW",
            staged_by=operator,
            native_content_hash=installed["content_hash"],
        )
        backend.save(state)
        return state


def review_staged(backend, client, candidate_id):
    state = backend.load(candidate_id)
    if state.get("code_release_id"):
        from analyst.code_releases import review

        return review(client, state["code_release_id"])
    installed = native_skill(client, state["skill_name"])
    if (
        not installed
        or installed["content_hash"] != state.get("native_content_hash")
        or state.get("status") != "STAGED_FOR_NATIVE_REVIEW"
    ):
        raise ValueError("Stage exact candidate bytes first")
    if installed.get("executable_review") and not installed.get("review_stale"):
        return {"status": "reused_exact_review", "content_hash": installed["content_hash"]}
    response = client.post(f"/api/skills/{state['skill_name']}/review", json={})
    response.raise_for_status()
    return response.json()


def enable(backend, client, candidate_id, expected_sha, operator):
    state = backend.load(candidate_id)
    if state.get("code_release_id"):
        from analyst.code_releases import enable as enable_package

        if expected_sha != state["candidate_sha"]:
            raise ValueError("Exact candidate SHA required")
        enable_package(backend, client, state["code_release_id"], operator)
        return backend.load(candidate_id)
    with backend.lock():
        state = backend.load(candidate_id)
        content = verified_candidate(backend, state, expected_sha, operator)
        if (backend.repo / state["artifact"]).read_text() != content:
            raise ValueError("Staged bytes changed")
        installed = native_skill(client, state["skill_name"])
        if (
            state.get("status") not in {"STAGED_FOR_NATIVE_REVIEW", "SKILL_ENABLED"}
            or not installed
            or installed["content_hash"] != state.get("native_content_hash")
            or not installed.get("executable_review")
            or installed.get("review_stale")
        ):
            raise ValueError("Current native exact-byte review required before enable")
        toggle(client, installed, True)
        state.update(status="SKILL_ENABLED", enabled_by=operator)
        return backend.save(state)


def rollback(backend, client, candidate_id, operator):
    if not operator.strip():
        raise ValueError("Operator is required")
    with backend.lock():
        state = backend.load(candidate_id)
        if state.get("code_release_id"):
            raise ValueError("Use code_release rollback for atomic whole-package restoration")
        if state.get("status") == "SKILL_ROLLED_BACK":
            return state
        if (
            backend.git("status", "--porcelain")
            or backend.git("symbolic-ref", "--short", "HEAD") != "main"
        ):
            raise ValueError("Clean evolution main required")
        actual = backend.git("show", f"HEAD:{state['artifact']}", raw=True)
        expected = backend.git("show", f"{state['candidate_sha']}:{state['artifact']}", raw=True)
        if actual != expected:
            raise ValueError("Skill has changed since this candidate; do not overwrite newer work")
        installed = native_skill(client, state["skill_name"])
        if installed and installed.get("enabled"):
            toggle(client, installed, False)
        # Revert only this candidate; later unrelated policy/skill commits survive.
        backend.git("revert", "--no-edit", state["candidate_sha"])
        state.update(
            status="SKILL_ROLLED_BACK",
            rolled_back_by=operator,
            rollback_sha=backend.git("rev-parse", "HEAD"),
        )
        return backend.save(state)
