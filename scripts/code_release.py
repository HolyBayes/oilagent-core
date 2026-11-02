"""Operator package release; stage → native restart/review → enable."""

import argparse
import json

import httpx
from dotenv import load_dotenv

from analyst.code_releases import abort, enable, prepare_rollback, review, seed, stage
from analyst.config import CORE_ROOT, evolution_repo, workspace
from analyst.evolution import Evolution
from analyst.method_runtime import active_bundle


def main():
    load_dotenv(CORE_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["seed", "stage", "review", "enable", "rollback", "abort", "status"]
    )
    parser.add_argument("id", nargs="?")
    parser.add_argument("--sha")
    parser.add_argument("--operator")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.action not in {"status", "review"} and not args.operator:
        parser.error("--operator required")
    backend = Evolution(workspace(), evolution_repo())
    if args.action == "seed":
        result = seed(backend, args.operator)
    elif args.action == "stage":
        if not args.id or not args.sha:
            parser.error("stage requires candidate ID and --sha")
        result = stage(backend, args.id, args.sha, args.operator)
    elif args.action in {"enable", "review"}:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.port}", trust_env=False, timeout=30
        ) as client:
            result = (
                enable(backend, client, args.id, args.operator)
                if args.action == "enable"
                else review(client, args.id)
            )
    elif args.action == "abort":
        result = abort(args.id, args.operator)
    elif args.action == "rollback":
        result = prepare_rollback(args.id, args.operator)
    else:
        bundle = active_bundle()
        result = bundle["release_id"] if bundle else "developer-seed"
    print(json.dumps({"release_id": result, "action": args.action}))


if __name__ == "__main__":
    main()
