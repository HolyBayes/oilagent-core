"""Fixed retrieval diagnostics without LLM calls; this does not score generated answers."""

import argparse
import json

from analyst.config import CORE_ROOT
from analyst.evidence import fit_context
from analyst.rag import ReportIndex, digest


def supported(case, rows):
    if case.get("check") == "publisher_coverage":
        return {r["publisher"] for r in rows} == {"OPEC", "EIA"}
    requirements = case.get("requirements") or [
        {
            "publisher": case["expected_publisher"],
            "page": case["expected_page"],
            "quote": case["supporting_text"],
        }
    ]
    return all(
        any(
            row["publisher"] == requirement["publisher"]
            and row["page"] == requirement["page"]
            and any(requirement["quote"] in row.get(field, "") for field in ["text", "page_intro"])
            for row in rows
        )
        for requirement in requirements
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument(
        "--baseline", action="store_true", help="Disable same-page introductory context"
    )
    args = parser.parse_args()
    name = "retrieval_cases.json" if args.split == "development" else "retrieval_holdout.json"
    cases = (CORE_ROOT / "data" / name).read_bytes()
    index, results = ReportIndex(), []
    for case in json.loads(cases):
        rows = index.search(case["question"], include_context=not args.baseline)
        selected = fit_context(rows, case["question"])
        results.append(
            {
                "case_id": case["case_id"],
                "retrieved": supported(case, rows),
                "in_context": supported(case, selected),
                "sources": [
                    {k: row[k] for k in ["publisher", "page", "offset"]} for row in selected
                ],
            }
        )
    print(
        json.dumps(
            {
                "split": args.split,
                "split_sha256": digest(cases),
                "baseline": args.baseline,
                "index": json.loads((index.directory / "index.json").read_text()),
                "summary": {k: sum(r[k] for r in results) for k in ["retrieved", "in_context"]},
                "total": len(results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
