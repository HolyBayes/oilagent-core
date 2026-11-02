"""Operator CLI: inspect, approve exact candidate SHA, or roll back a checked bundle."""

import argparse
import json

from analyst.config import evolution_repo, workspace
from analyst.evolution import Evolution
from analyst.releases import active_release, publish, rollback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    approve = sub.add_parser("approve")
    approve.add_argument("candidate_id")
    approve.add_argument("--sha", required=True)
    approve.add_argument("--operator", required=True)
    undo = sub.add_parser("rollback")
    undo.add_argument("release_id")
    args = parser.parse_args()
    if args.action == "status":
        result = active_release()
    elif args.action == "approve":
        result = {
            "release_id": publish(
                Evolution(workspace(), evolution_repo()), args.candidate_id, args.sha, args.operator
            )
        }
    else:
        result = {"release_id": rollback(args.release_id)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
