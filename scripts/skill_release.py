"""Operator CLI for skill staging, native review, enabling and rollback."""

import argparse
import json

import httpx
from dotenv import load_dotenv

from analyst.config import CORE_ROOT, evolution_repo, workspace
from analyst.evolution import Evolution
from analyst.skill_release import enable, review_staged, rollback, stage


def main():
    load_dotenv(CORE_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "review", "enable", "rollback"])
    parser.add_argument("candidate_id")
    parser.add_argument("--sha")
    parser.add_argument("--operator")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.action != "review" and not args.operator:
        parser.error("--operator is required")
    if args.action in {"stage", "enable"} and not args.sha:
        parser.error("--sha must name the exact evaluated candidate")
    backend = Evolution(workspace(), evolution_repo())
    with httpx.Client(
        base_url=f"http://127.0.0.1:{args.port}", trust_env=False, timeout=30
    ) as client:
        if args.action == "review":
            result = review_staged(backend, client, args.candidate_id)
        elif args.action == "rollback":
            result = rollback(backend, client, args.candidate_id, args.operator)
        else:
            result = {"stage": stage, "enable": enable}[args.action](
                backend, client, args.candidate_id, args.sha, args.operator
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
