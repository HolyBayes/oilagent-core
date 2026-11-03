import json

import httpx
import pytest

from analyst import code_evaluation as evaluation
from analyst import code_releases as releases
from analyst.code_packages import artifact, package_digest, propose, repository_files, seed_source
from analyst.evolution import Evolution, fingerprint
from analyst.method_runtime import active_bundle, code_root, method_session, run, source_for


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path / "runtime"))
    monkeypatch.setenv("RELEASE_PATH", str(tmp_path / "releases"))
    monkeypatch.setenv("EVOLUTION_REPO_PATH", str(tmp_path / "evolution"))
    current = {"core": "v1", "runner": {"image": "sha256:" + "1" * 64}}
    monkeypatch.setattr(releases, "evaluation_identity", lambda: dict(current))
    monkeypatch.setattr(evaluation, "evaluation_identity", lambda: dict(current))
    return Evolution(tmp_path / "runtime"), current


def native_client(release_id, *, clean=True):
    files = releases.read_bundle(release_id)["files"]
    cards = {
        p.split("/")[1]: {
            "name": p.split("/")[1],
            "content_hash": releases.package_hash(files, p.split("/")[1]),
            "executable_review": clean,
            "review_stale": False,
            "enabled": False,
        }
        for p in files
        if p.endswith("/SKILL.md")
    }

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"skills": list(cards.values())})
        name = request.url.path.split("/")[3]
        body = json.loads(request.content)
        assert body["expected_content_hash"] == cards[name]["content_hash"]
        cards[name]["enabled"] = body["enabled"]
        return httpx.Response(200, json={"enabled": body["enabled"]})

    return httpx.Client(base_url="http://native", transport=httpx.MockTransport(handle)), cards


def activate_seed(backend):
    release_id = releases.seed(backend, "test-operator")
    client, _ = native_client(release_id)
    with client:
        releases.enable(backend, client, release_id, "test-operator")
    return release_id


def approved_code(backend):
    state = propose(
        backend,
        backend.baseline()["base_sha"],
        "search_strategy",
        seed_source("search_strategy") + "\n# Candidate fixture.\n",
        "Gate test only",
        "fixture",
        "release-fixture",
    )
    state["quality_checks"] = {
        "passed": True,
        "identity": releases.evaluation_identity(),
        "candidate_sha": state["candidate_sha"],
        "active_release_id": evaluation.active_id(),
        "package_sha256": package_digest(repository_files(backend, state["candidate_sha"])),
    }
    state["critic"] = {
        "verdict": "APPROVE",
        "candidate_sha": state["candidate_sha"],
        "checks_sha256": fingerprint(state["quality_checks"]),
    }
    backend.save(state)
    return state


def test_seed_requires_whole_package_review_and_blocks_execution(installation):
    backend, _ = installation
    release_id = releases.seed(backend, "test-operator")
    with pytest.raises(ValueError, match="being activated"):
        run("scenario", {})
    client, cards = native_client(release_id, clean=False)
    with client:
        with pytest.raises(ValueError, match="exact-package"):
            releases.enable(backend, client, release_id, "test-operator")
        assert active_bundle() is None and (code_root() / "maintenance.json").exists()
        for card in cards.values():
            card["executable_review"] = True
        releases.enable(backend, client, release_id, "test-operator")
    assert active_bundle()["release_id"] == release_id
    assert not (code_root() / "maintenance.json").exists()
    assert not any(c["enabled"] for c in cards.values())


def test_release_pins_methods_and_rollback_restores_main_preserving_other_files(installation):
    backend, _ = installation
    initial = activate_seed(backend)
    state = approved_code(backend)
    release_id = releases.stage(backend, state["candidate_id"], state["candidate_sha"], "operator")
    assert backend.baseline()["base_sha"] == state["base_sha"]
    client, _ = native_client(release_id)
    with client, method_session():
        original = source_for("search_strategy")
        releases.enable(backend, client, release_id, "operator")
        assert source_for("search_strategy") == original
    assert source_for("search_strategy") != original
    extra = backend.repo / "unrelated.txt"
    extra.write_text("preserve")
    backend.git("add", "unrelated.txt")
    backend.git("commit", "-m", "Unrelated commit")
    undo = releases.prepare_rollback(initial, "operator")
    client, _ = native_client(undo)
    with client:
        releases.enable(backend, client, undo, "operator")
    assert (backend.repo / artifact("search_strategy")).read_text() == original
    assert extra.read_text() == "preserve"
    assert active_bundle()["files"] == releases.read_bundle(initial)["files"]


def test_tampering_stale_identity_and_conflicting_stage_are_rejected(installation):
    backend, current = installation
    initial = activate_seed(backend)
    state = approved_code(backend)
    state["critic"]["checks_sha256"] = "bad"
    backend.save(state)
    with pytest.raises(ValueError, match="exact critic"):
        releases.stage(backend, state["candidate_id"], state["candidate_sha"], "operator")
    current["core"] = "v2"
    with pytest.raises(ValueError, match="changed"):
        releases.read_bundle(initial)
    assert releases.read_bundle(initial, historical=True)["release_id"] == initial
    with pytest.raises(ValueError, match="exact critic"):
        releases.stage(backend, state["candidate_id"], state["candidate_sha"], "operator")


def test_aborted_stage_keeps_admission_closed_until_native_restoration(installation):
    backend, _ = installation
    initial = activate_seed(backend)
    state = approved_code(backend)
    staged = releases.stage(backend, state["candidate_id"], state["candidate_sha"], "operator")
    with pytest.raises(ValueError, match="already staged"):
        releases.freeze(releases.read_bundle(initial)["files"], {"kind": "test"})
    assert releases.abort(staged, "operator") == initial
    assert (code_root() / "maintenance.json").exists()
    client, _ = native_client(initial)
    with client:
        releases.enable(backend, client, initial, "operator")
    assert not (code_root() / "maintenance.json").exists()
    assert backend.baseline()["base_sha"] == state["base_sha"]


def test_metrics_reject_regression_even_with_aggregate_gain():
    assert evaluation.compare("search_strategy", [0, 1, 0], [1, 1, 1])["passed"]
    assert not evaluation.compare("search_strategy", [0, 1, 0], [1, 0, 1])["passed"]
    before = [{"mae": 2.0, "coverage": 0.8, "width": 10.0}]
    assert evaluation.compare("forecast", before, [{"mae": 1.0, "coverage": 0.8, "width": 10.0}])[
        "passed"
    ]
    assert not evaluation.compare(
        "forecast", before, [{"mae": 1.0, "coverage": 0.7, "width": 10.0}]
    )["passed"]
    assert not evaluation.compare(
        "forecast", before, [{"mae": 1.0, "coverage": 0.8, "width": 15.0}]
    )["passed"]


def test_runtime_upgrade_requires_same_packages_data_and_no_regressions(installation, monkeypatch):
    from analyst.config import CORE_ROOT

    monkeypatch.syspath_prepend(str(CORE_ROOT))
    from scripts import qualify_runtime as qualifier

    backend, current = installation
    current["datasets"] = {"fixed": "v1"}
    initial = activate_seed(backend)
    metrics = {
        slot: ([{"mae": 2.0, "coverage": 0.8, "width": 10.0}] if slot == "forecast" else [1, 0])
        for slot in releases.SLOTS
    }
    monkeypatch.setattr(qualifier, "evaluation_identity", lambda: dict(current))
    monkeypatch.setattr(qualifier, "measure", lambda files: metrics)
    receipt_id = qualifier.capture("operator")
    current["core"] = "v2"
    current["datasets"] = {"fixed": "v2"}
    with pytest.raises(ValueError, match="Dataset changed"):
        qualifier.qualify(backend, receipt_id, "operator")
    current["datasets"] = {"fixed": "v1"}
    metrics["scenario"] = [0, 0]
    with pytest.raises(ValueError, match="regresses"):
        qualifier.qualify(backend, receipt_id, "operator")
    metrics["scenario"] = [1, 0]
    upgraded = qualifier.qualify(backend, receipt_id, "operator")
    assert releases.read_bundle(upgraded)["kind"] == "runtime-requalified"
    assert (
        releases.read_bundle(upgraded)["files"]
        == releases.read_bundle(initial, historical=True)["files"]
    )
    current["core"] = "v3"
    restaged = qualifier.qualify(backend, receipt_id, "operator")
    assert restaged != upgraded
    assert releases.read_bundle(restaged)["identity"]["core"] == "v3"


def test_runtime_qualification_cannot_smuggle_changed_methods(installation, monkeypatch):
    from analyst.config import CORE_ROOT

    monkeypatch.syspath_prepend(str(CORE_ROOT))
    from scripts import qualify_runtime as qualifier

    backend, current = installation
    current["datasets"] = {}
    activate_seed(backend)
    monkeypatch.setattr(qualifier, "evaluation_identity", lambda: dict(current))
    monkeypatch.setattr(qualifier, "measure", lambda files: {})
    receipt = qualifier.capture("operator")
    path = backend.repo / artifact("scenario")
    path.write_text(path.read_text() + "\n")
    backend.git("add", "--", artifact("scenario"))
    backend.git("commit", "-m", "Changed method")
    with pytest.raises(ValueError, match="cannot change skill"):
        qualifier.qualify(backend, receipt, "operator")


def test_package_updates_preserve_disabled_skill_switches(installation):
    backend, _ = installation
    initial = activate_seed(backend)
    updated = releases.freeze(
        releases.read_bundle(initial)["files"],
        {
            "kind": "runtime-requalified",
            "source_commit": backend.baseline()["base_sha"],
            "previous_release_id": initial,
        },
    )
    client, cards = native_client(updated)
    for name, card in cards.items():
        card["enabled"] = name != "oil_forecast"
    before = {name: card["enabled"] for name, card in cards.items()}
    with client:
        releases.enable(backend, client, updated, "operator")
    assert before == {name: card["enabled"] for name, card in cards.items()}


@pytest.mark.parametrize("tamper", [None, "method", "seed", "dataset", "regression"])
def test_explicit_query_extension_cannot_change_other_code_or_old_gold(
    installation, monkeypatch, tamper
):
    import copy

    from analyst.code_packages import query_strategy_extension
    from analyst.config import CORE_ROOT
    from analyst.evolution import atomic_json
    from analyst.releases import canonical, sha

    monkeypatch.syspath_prepend(str(CORE_ROOT))
    from scripts import qualify_runtime as qualifier

    backend, current = installation
    current["datasets"] = {"old-gold": "v1"}
    old = repository_files(backend, backend.baseline()["base_sha"])
    old.pop(artifact("query_strategy"))
    bundle = {"files": old, "identity": copy.deepcopy(current), "kind": "fixture-legacy"}
    raw = canonical(bundle)
    old_id = sha(raw)
    root = code_root()
    (root / "bundles").mkdir(parents=True)
    (root / "bundles" / (old_id + ".json")).write_bytes(raw)
    atomic_json(root / "active.json", {"release_id": old_id})
    with pytest.raises(ValueError, match="Missing executable"):
        releases.read_bundle(old_id)
    metrics = {
        slot: ([{"mae": 2.0, "coverage": 0.8, "width": 10.0}] if slot == "forecast" else [1, 0])
        for slot in releases.SLOTS
        if slot != "query_strategy"
    }
    receipt = {
        "release_id": old_id,
        "identity": bundle["identity"],
        "package_sha256": package_digest(old),
        "metrics": metrics,
    }
    raw = canonical(receipt)
    receipt_id = sha(raw)
    (root / "qualifications").mkdir()
    (root / "qualifications" / (receipt_id + ".json")).write_bytes(raw)
    files = query_strategy_extension(old)
    for name, content in files.items():
        (backend.repo / name).write_text(content)
    if tamper in {"method", "seed"}:
        name = artifact("scenario" if tamper == "method" else "query_strategy")
        (backend.repo / name).write_text(files[name] + "\n")
    backend.git("add", "--", "ouroboros_skills")
    backend.git("commit", "-m", "Developer strategy extension fixture")
    current["core"] = "v2"
    current["datasets"] = {
        "old-gold": "v2" if tamper == "dataset" else "v1",
        "rag_eval.json": "new-replay",
    }
    after = copy.deepcopy(metrics)
    for slot in ["chunking", "reranking"]:
        after[slot] += [0.5]
    after["query_strategy"] = [0.5]
    if tamper == "regression":
        after["reranking"][0] = 0
    monkeypatch.setattr(qualifier, "measure", lambda files: after)
    monkeypatch.setattr(qualifier, "evaluation_identity", lambda: copy.deepcopy(current))
    if tamper:
        with pytest.raises(ValueError):
            qualifier.qualify(backend, receipt_id, "operator", add_query_strategy=True)
        assert not (root / "prepared.json").exists()
    else:
        upgraded = qualifier.qualify(backend, receipt_id, "operator", add_query_strategy=True)
        new = releases.read_bundle(upgraded)
        assert new["kind"] == "runtime-extended"
        assert new["qualification"]["query_strategy"]["gain"] == 0
        assert new["qualification"]["reranking"]["before"] == [1, 0, 0.5]
        assert releases.package_hash(new["files"], "report_rag") != releases.package_hash(
            old, "report_rag"
        )
        assert evaluation.active_id() == old_id


def test_submitted_evolution_matches_bootstrap_seeds(tmp_path):
    from analyst.code_packages import SLOTS, seed_source
    from analyst.config import CORE_ROOT
    from analyst.evolution import Evolution

    submitted = CORE_ROOT.parent / "evolution"
    if not submitted.exists():
        pytest.skip("Independent checkout not present")
    backend = Evolution(tmp_path / "runtime", tmp_path / "evolution")
    for slot in SLOTS:
        assert (submitted / artifact(slot)).read_text() == seed_source(slot)
        assert (backend.repo / artifact(slot)).read_text() == seed_source(slot)
