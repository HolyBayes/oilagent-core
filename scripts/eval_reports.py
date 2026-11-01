"""Development retrieval diagnostics on the locked corpus; no LLM calls or blind claims."""

import json

from analyst.config import CORE_ROOT
from analyst.rag import ReportIndex

if __name__ == "__main__":
    index = ReportIndex()
    results = []
    for case in json.loads((CORE_ROOT / "data/retrieval_cases.json").read_text()):
        rows = index.search(case["question"])
        if case["check"] == "publisher_coverage":
            passed = {r["publisher"] for r in rows} == {"OPEC", "EIA"}
        else:
            passed = any(
                r["publisher"] == case["expected_publisher"]
                and r["page"] == case["expected_page"]
                and case["supporting_text"] in r["text"]
                for r in rows
            )
        results.append(
            {
                **case,
                "passed": passed,
                "retrieved": [{k: row[k] for k in ["publisher", "page", "offset"]} for row in rows],
            }
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))
