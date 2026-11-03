"""Paired evaluation on a fixed operator-owned PDF support dataset."""

import json
import os

from analyst.config import configured_path
from analyst.evidence import fit_context, supporting_passages
from analyst.rag import ReportIndex
from analyst.releases import active_release, identity, sha


def supported(case, rows):
    if case.get("check") == "publisher_coverage":
        return {"OPEC", "EIA"} <= {r["publisher"] for r in rows}
    requirements = case.get("requirements") or [
        {
            "publisher": case["expected_publisher"],
            "page": case["expected_page"],
            "quote": case["supporting_text"],
        }
    ]
    return all(
        any(
            row["publisher"] == expected["publisher"]
            and row["page"] == expected["page"]
            and any(expected["quote"] in text for text in supporting_passages(row))
            for row in rows
        )
        for expected in requirements
    )


def support_score(case, rows):
    """All required quotes must survive; earlier complete support scores higher."""
    if not supported(case, rows):
        return 0.0
    if case.get("check") == "publisher_coverage":
        positions = [
            next(i for i, r in enumerate(rows, 1) if r["publisher"] == p) for p in ["OPEC", "EIA"]
        ]
    else:
        requirements = case.get("requirements") or [
            {
                "publisher": case["expected_publisher"],
                "page": case["expected_page"],
                "quote": case["supporting_text"],
            }
        ]
        positions = [
            next(i for i, row in enumerate(rows, 1) if supported({"requirements": [r]}, [row]))
            for r in requirements
        ]
    return sum(1 / p for p in positions) / len(positions)


def evaluate(candidate_policy, index=None):
    path = configured_path("EVOLUTION_EVAL_PATH", "data/evolution_eval.json")
    content = path.read_bytes()
    cases = json.loads(content)
    if not cases or len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("Evaluation cases must be nonempty and unique")
    baseline = active_release()
    index = index or ReportIndex()
    before, after, regressions = 0, 0, []
    splits = {}
    for case in cases:
        old = fit_context(
            index.search(case["question"], policy=baseline["policy"]), case["question"]
        )
        new = fit_context(index.search(case["question"], policy=candidate_policy), case["question"])
        old_ok, new_ok = supported(case, old), supported(case, new)
        split = splits.setdefault(
            case.get("split", "development"), {"before": 0, "after": 0, "total": 0}
        )
        split["before"] += int(old_ok)
        split["after"] += int(new_ok)
        split["total"] += 1
        before += old_ok
        after += new_ok
        if old_ok and not new_ok:
            regressions.append(case["case_id"])
    improvement = (after - before) / len(cases)
    return {
        "passed": (
            splits.get("development", {}).get("after", 0)
            > splits.get("development", {}).get("before", 0)
        )
        and not regressions
        and improvement >= float(os.getenv("EVOLUTION_MIN_GAIN", ".01")),
        "scope": "paired PDF retrieval support; not answer faithfulness or unseen-market accuracy",
        "splits": splits,
        "total": len(cases),
        "before": before,
        "after": after,
        "regressions": regressions,
        "gain": improvement,
        "eval_sha256": sha(content),
        "identity": identity(),
        "active_release_id": baseline["release_id"],
        "baseline_policy": baseline["policy"],
        "candidate_policy": candidate_policy,
        "model": index.embedding,
        "threshold": float(os.getenv("EVOLUTION_MIN_GAIN", ".01")),
    }
