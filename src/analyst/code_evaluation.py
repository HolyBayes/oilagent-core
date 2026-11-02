"""Protected paired metrics. No evaluator/test targets enter the candidate container."""

import json
import math
import time
from itertools import product

import numpy as np

from analyst.capabilities import trusted_evaluation
from analyst.code_executor import runner_identity
from analyst.code_packages import SLOTS, artifact, repository_files, validate_source
from analyst.config import CORE_ROOT
from analyst.method_contracts import validate
from analyst.method_runtime import code_root, method_overrides, method_pin
from analyst.releases import identity, sha


def evaluation_identity():
    datasets = [
        "code_eval.json",
        "evolution_eval.json",
        "reports.json",
        "brent_daily.csv",
        "brent_daily.json",
    ]
    return {
        **identity(),
        "runner": runner_identity(),
        "datasets": {name: sha((CORE_ROOT / "data" / name).read_bytes()) for name in datasets},
    }


def active_id():
    pointer = code_root() / "active.json"
    return json.loads(pointer.read_text())["release_id"] if pointer.exists() else "developer-seed"


@trusted_evaluation()
def score(slot, source, cases):
    from analyst.method_runtime import run_many

    if slot == "forecast":
        from analyst.forecast import forecast_brent

        token = method_overrides.set({slot: source})
        try:
            values = []
            for case in cases["forecast"]:
                result = forecast_brent(6, **case, path=CORE_ROOT / "data/brent_daily.csv")
                for model in ["ARIMA", "ETS"]:
                    for row in result["backtest_by_horizon"][model]:
                        values.append(
                            {
                                "mae": row["mae"],
                                "coverage": row["coverage"],
                                "width": row["mean_interval_width"],
                            }
                        )
            return values
        finally:
            method_overrides.reset(token)
    if slot in {"reranking", "chunking"}:
        from analyst.evidence import fit_context
        from analyst.quality import supported
        from analyst.rag import ReportIndex

        token = method_overrides.set({slot: source})
        try:
            index = ReportIndex()
            if slot == "chunking":
                index.ingest()
            gold = json.loads((CORE_ROOT / "data/evolution_eval.json").read_text())
            return [
                int(supported(case, fit_context(index.search(case["question"]), case["question"])))
                for case in gold
            ]
        finally:
            method_overrides.reset(token)
    requests = [{k: v for k, v in c.items() if k != "expected_first"} for c in cases[slot]]
    results = run_many(slot, requests, source)
    values = []
    for case, request, result in zip(cases[slot], requests, results):
        output = validate(slot, request, result)
        if slot == "search_strategy":
            values.append(int(output[0] == case["expected_first"]))
        else:
            expected = [
                request["initial_price"]
                * math.exp(math.log1p(-request["cut_mbd"] / request["supply_mbd"]) / (d - s))
                for d, s in product(request["demand_elasticity"], request["supply_elasticity"])
            ]
            values.append(int(np.allclose(output, expected, rtol=1e-10, atol=1e-10)))
    return values


def compare(slot, before, after):
    if len(before) != len(after) or not before:
        raise ValueError("Paired evaluation size mismatch")
    if slot == "forecast":
        regressions = [
            i
            for i, (a, b) in enumerate(zip(before, after))
            if b["mae"] > a["mae"] + 1e-8
            or b["coverage"] + 1e-8 < a["coverage"]
            or b["width"] > a["width"] * 1.1 + 1e-8
        ]
        old = float(np.mean([v["mae"] for v in before]))
        new = float(np.mean([v["mae"] for v in after]))
        gain = (old - new) / max(old, 1e-9)
    else:
        regressions = [i for i, (a, b) in enumerate(zip(before, after)) if b < a]
        gain = (sum(after) - sum(before)) / len(before)
    return {
        "passed": not regressions and gain >= 0.01,
        "gain": gain,
        "regressions": regressions,
        "before": before,
        "after": after,
        "threshold": 0.01,
    }


def evaluate(backend, state, current):
    paths = backend.git(
        "diff", "--name-only", state["base_sha"], state["candidate_sha"]
    ).splitlines()
    if sorted(paths) != state["artifacts"]:
        raise ValueError("Protected files changed")
    slot = state["code_slot"]
    files = repository_files(backend, state["candidate_sha"])
    for name in SLOTS:
        validate_source(name, files[artifact(name)])
    source = files[artifact(slot)]
    if sha(source.encode()) != state["content_sha256"]:
        raise ValueError("Source hash mismatch")
    cases = json.loads((CORE_ROOT / "data/code_eval.json").read_text())
    from analyst.code_packages import seed_source

    baseline_id = active_id()
    if baseline_id == "developer-seed":
        baseline_sources = {name: seed_source(name) for name in SLOTS}
    else:
        from analyst.code_releases import read_bundle

        previous = read_bundle(baseline_id, historical=True)
        baseline_sources = {name: previous["files"][artifact(name)] for name in SLOTS}
    for name in SLOTS:
        if name != slot and files[artifact(name)] != baseline_sources[name]:
            raise ValueError(
                "Unchanged methods differ from serving baseline; synchronize main first"
            )
    from analyst.code_executor import execution_budget

    budget = execution_budget.set({"calls": 0, "deadline": time.monotonic() + 300})
    token = method_pin.set(baseline_sources)
    try:
        before = score(slot, baseline_sources[slot], cases)
        after = score(slot, source, cases)
    finally:
        method_pin.reset(token)
        execution_budget.reset(budget)
    if evaluation_identity() != current:
        raise ValueError("Executor/core/dataset changed during evaluation")
    return {
        **compare(slot, before, after),
        "candidate_sha": state["candidate_sha"],
        "identity": current,
        "active_release_id": active_id(),
        "package_sha256": sha(json.dumps(files, sort_keys=True).encode()),
        "scope": (
            "Fixed paired method metrics; not unseen-data accuracy or proof of algorithm identity"
        ),
    }
