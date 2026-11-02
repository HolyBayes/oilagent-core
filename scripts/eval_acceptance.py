"""Run fixed local PDF and deterministic acceptance cases without LLM calls."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from analyst.budget import Budget, BudgetExceeded
from analyst.config import CORE_ROOT
from analyst.contracts import ReportClaim, ReportDraft, Route
from analyst.evidence import compare_claims, fit_context, validate_claims
from analyst.graph import answer_question
from analyst.quality import supported
from analyst.rag import ReportIndex
from analyst.releases import sha
from analyst.scenario import supply_cut_scenario


def check(case, index):
    kind = case["kind"]
    if kind == "retrieval":
        return supported(case, fit_context(index.search(case["question"]), case["question"]))
    if kind == "scenario":
        try:
            result = supply_cut_scenario(case["inputs"])
            return case["valid"] and result["price_range"][0] > case["inputs"]["initial_price"]
        except ValueError:
            return not case["valid"]
    if kind == "comparison":
        common = dict(
            kind="fact",
            metric="demand growth",
            geography="global",
            unit="mb/d",
            period="2026",
            vintage="2025-10",
            observation_type="forecast",
        )
        a = {**common, "source_id": "R1", "value": "1.3"}
        b = {**common, "source_id": "R2", "value": "0.9", **case["change"]}
        result, warning = compare_claims([a, b])
        return (bool(result) == case["valid"]) and (bool(warning) != case["valid"])
    if kind == "claim":
        source = dict(source_id="R1", numeric_verified=True, text="Price 52 in 2026.")
        claim = ReportClaim(
            **{
                "source_id": "R1",
                "text": "Price 52 in 2026",
                "quote": source["text"],
                **case["change"],
            }
        )
        accepted, _ = validate_claims(ReportDraft(claims=[claim], abstain=False), [source])
        return bool(accepted) == case["valid"]
    if kind == "workflow":
        route = Route(intent=case["intent"], freshness_required=False)
        with (
            patch("analyst.graph.model_ready", return_value=True),
            patch("analyst.graph.invoke_structured", return_value=(route, {})),
        ):
            return answer_question("Контрольный запрос")["status"] == case["expected_status"]
    if kind == "budget":
        with patch.dict("os.environ", {"REQUEST_MAX_TOOLS": "0"}):
            try:
                Budget().tool("must not run")
            except BudgetExceeded:
                return True
        return False
    raise ValueError("Unknown acceptance kind")


def main():
    path = CORE_ROOT / "data/acceptance_cases.json"
    content = path.read_bytes()
    dataset = json.loads(content)
    index = ReportIndex()
    results = []
    with (
        tempfile.TemporaryDirectory() as directory,
        patch.dict(
            "os.environ",
            {
                "SESSION_DB_PATH": str(Path(directory) / "sessions.sqlite3"),
                "TRACE_PATH": str(Path(directory) / "traces"),
            },
        ),
    ):
        for case in dataset["cases"]:
            results.append(
                {
                    "case_id": case["case_id"],
                    "kind": case["kind"],
                    "passed": bool(check(case, index)),
                }
            )
    print(
        json.dumps(
            {
                "dataset_sha256": sha(content),
                "scope": dataset["scope"],
                "llm_calls": 0,
                "passed": sum(r["passed"] for r in results),
                "total": len(results),
                "cases": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
