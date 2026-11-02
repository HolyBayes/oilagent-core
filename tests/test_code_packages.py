import pytest

from analyst.code_packages import propose, snapshot
from analyst.evolution import Evolution


def test_code_candidate_is_immutable_and_cannot_activate_without_evaluation(tmp_path):
    backend = Evolution(tmp_path)
    base = backend.baseline()["base_sha"]
    source = 'def run(request):\n    return {"value": 42}\n'
    state = propose(backend, base, "forecast", source, "experiment", "fixture", "code-1")
    assert backend.baseline()["base_sha"] == base
    assert snapshot(backend, state["candidate_sha"], "forecast")["source"] == source
    assert (backend.repo / state["artifact"]).read_text() == snapshot(backend, base, "forecast")[
        "source"
    ]
    checked = backend.checks(state["candidate_id"], real=True)
    assert checked["status"] == "CODE_EVALUATION_UNAVAILABLE"
    with pytest.raises(ValueError, match="Checks"):
        backend.review(state["candidate_id"])
    with pytest.raises(ValueError, match="conflicts"):
        propose(backend, base, "forecast", source + "\n", "experiment", "fixture", "code-1")


def test_candidate_cannot_name_a_protected_core_file(tmp_path):
    backend = Evolution(tmp_path)
    with pytest.raises(ValueError, match="Unknown"):
        propose(
            backend,
            backend.baseline()["base_sha"],
            "../../core/evaluation",
            "def run(request): return 1",
            "bad",
            "fixture",
            "code-2",
        )


def test_unavailable_rerun_clears_previous_pass_and_blocks_critic(tmp_path, monkeypatch):
    import analyst.code_evaluation as evaluator

    backend = Evolution(tmp_path)
    state = propose(
        backend,
        backend.baseline()["base_sha"],
        "forecast",
        "def run(request): return {}\n",
        "fixture",
        "fixture",
        "rerun-failure",
    )
    state["quality_checks"] = {"passed": True, "identity": {"old": True}}
    backend.save(state)

    def unavailable():
        raise ConnectionError("Executor unavailable")

    monkeypatch.setattr(evaluator, "evaluation_identity", unavailable)
    state = backend.checks(state["candidate_id"], real=True)
    assert state["status"] == "CODE_EVALUATION_UNAVAILABLE"
    assert not state["quality_checks"]["passed"]
    with pytest.raises(ValueError, match="Checks"):
        backend.review(state["candidate_id"])
