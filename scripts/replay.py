"""Recheck frozen response evidence without contacting providers or executing tools."""

import argparse
import json
from uuid import UUID

from analyst.config import configured_path
from analyst.contracts import ReportDraft
from analyst.evidence import validate_claims
from analyst.releases import identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id")
    args = parser.parse_args()
    request_id = str(UUID(args.request_id))
    state = json.loads(
        (configured_path("TRACE_PATH", "workspace/traces") / f"{request_id}.json").read_text()
    )
    draft = ReportDraft(claims=state.get("claims", []), abstain=False)
    claims, warnings = validate_claims(draft, state.get("evidence", []))
    print(
        json.dumps(
            {
                "request_id": request_id,
                "network_used": False,
                "llm_calls": 0,
                "same_core_source": state.get("versions", {}).get("core_source_sha256")
                == identity()["core_source_sha256"],
                "verified_claims": len(claims),
                "warnings": warnings,
                "answer": state["answer"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
