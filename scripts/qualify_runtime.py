"""Operator runtime upgrade: capture old metrics, redeploy, qualify identical skill bytes."""

import argparse
import json
from datetime import datetime, timezone

from dotenv import load_dotenv

from analyst.code_evaluation import active_id, compare, evaluation_identity, score
from analyst.code_packages import (
    SLOTS,
    artifact,
    package_digest,
    query_strategy_extension,
    repository_files,
)
from analyst.code_releases import freeze, read_bundle, release_lock
from analyst.config import CORE_ROOT, evolution_repo, workspace
from analyst.evolution import Evolution
from analyst.method_runtime import code_root, method_pin
from analyst.releases import canonical, sha


def measure(files):
    cases = json.loads((CORE_ROOT / "data/code_eval.json").read_text())
    sources = {slot: files[artifact(slot)] for slot in SLOTS}
    token = method_pin.set(sources)
    try:
        return {slot: score(slot, source, cases) for slot, source in sources.items()}
    finally:
        method_pin.reset(token)


def capture(operator):
    bundle = read_bundle(active_id())
    current = evaluation_identity()
    metrics = measure(bundle["files"])
    if evaluation_identity() != current:
        raise ValueError("Runtime changed during measurement")
    receipt = {
        "release_id": bundle["release_id"],
        "identity": current,
        "package_sha256": package_digest(bundle["files"]),
        "metrics": metrics,
        "operator": operator,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    raw = canonical(receipt)
    receipt_id = sha(raw)
    path = code_root() / "qualifications" / (receipt_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o444)
    return receipt_id


def qualify(backend, receipt_id, operator, *, add_query_strategy=False):
    import re

    if not re.fullmatch(r"[0-9a-f]{64}", receipt_id):
        raise ValueError("Exact receipt hash required")
    raw = (code_root() / "qualifications" / (receipt_id + ".json")).read_bytes()
    if sha(raw) != receipt_id:
        raise ValueError("Qualification receipt corrupted")
    receipt = json.loads(raw)
    if active_id() != receipt["release_id"]:
        raise ValueError("Serving release changed after capture")
    old = read_bundle(receipt["release_id"], historical=True)
    if old["identity"] != receipt["identity"]:
        raise ValueError("Captured runtime differs from the original release")
    files = repository_files(backend, backend.baseline()["base_sha"])
    if (
        files != (query_strategy_extension(old["files"]) if add_query_strategy else old["files"])
        or package_digest(old["files"]) != receipt["package_sha256"]
        or backend.git("status", "--porcelain")
    ):
        raise ValueError("Runtime qualification cannot change skill source")
    current = evaluation_identity()
    datasets = dict(current["datasets"])
    if add_query_strategy:
        datasets.pop("rag_eval.json", None)
    if datasets != receipt["identity"]["datasets"]:
        raise ValueError("Dataset changed; this is not a runtime-only upgrade")
    kind = "runtime-extended" if add_query_strategy else "runtime-requalified"
    prepared = code_root() / "prepared.json"
    if prepared.exists():
        pending = read_bundle(json.loads(prepared.read_text())["release_id"], historical=True)
        if (
            pending.get("kind") != kind
            or pending.get("qualification_receipt") != receipt_id
            or pending["files"] != files
            or current == receipt["identity"]
        ):
            raise ValueError("A different package is staged")
        # The active release has a stale identity and cannot admit methods.
        # Replace only this interrupted qualification, then measure again.
        prepared.unlink()
        (code_root() / "maintenance.json").unlink(missing_ok=True)
    after = measure(files)
    comparisons = {}
    for slot in SLOTS:
        before = receipt["metrics"].get(slot)
        if add_query_strategy and slot == "query_strategy":
            before = after[slot]
        elif add_query_strategy and slot in {"reranking", "chunking"}:
            before = before + after[slot][len(before) :]
        comparisons[slot] = compare(slot, before, after[slot])
    if any(row["regressions"] for row in comparisons.values()):
        raise ValueError("New runtime regresses on fixed method metrics")
    if current != evaluation_identity():
        raise ValueError("Runtime changed during qualification")
    return freeze(
        files,
        {
            "kind": kind,
            "source_commit": backend.baseline()["base_sha"],
            "previous_release_id": receipt["release_id"],
            "qualification_receipt": receipt_id,
            "qualification": comparisons,
            "approved_by": operator,
            "scope": (
                "Exact developer query-strategy extension; new replay metrics initialized, "
                "existing metrics must not regress; no improvement claim"
                if add_query_strategy
                else "Same skill bytes under a changed runtime; no improvement claim"
            ),
        },
    )


def main():
    load_dotenv(CORE_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "qualify"])
    parser.add_argument("receipt_id", nargs="?")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--add-query-strategy", action="store_true")
    args = parser.parse_args()
    if not args.operator.strip():
        parser.error("Operator required")
    backend = Evolution(workspace(), evolution_repo())
    with release_lock(), backend.lock():
        if args.action == "capture":
            result = capture(args.operator)
        else:
            if not args.receipt_id:
                parser.error("Receipt required")
            result = qualify(
                backend, args.receipt_id, args.operator, add_query_strategy=args.add_query_strategy
            )
    print(json.dumps({"action": args.action, "id": result}))


if __name__ == "__main__":
    main()
