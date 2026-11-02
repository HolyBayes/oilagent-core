"""Versioned capability source packages; no host imports or automatic activation."""

import ast
import hashlib
import json

SLOTS = {
    "forecast": "oil_forecast",
    "scenario": "oil_forecast",
    "chunking": "report_rag",
    "reranking": "report_rag",
    "search_strategy": "web_research",
}


def artifact(slot):
    if slot not in SLOTS:
        raise ValueError("Unknown executable capability")
    return f"ouroboros_skills/{SLOTS[slot]}/{slot}.py"


def validate_source(slot, source):
    artifact(slot)
    if not isinstance(source, str) or not 1 <= len(source.encode()) <= 64000:
        raise ValueError("Source must contain 1..64000 UTF-8 bytes")
    tree = ast.parse(source)
    if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
        raise ValueError("Capability must export run(request)")
    # AST validation is a packaging check. Container isolation is the execution boundary.
    return hashlib.sha256(source.encode()).hexdigest()


def manifest(slot, source):
    return {
        "slot": slot,
        "artifact": artifact(slot),
        "abi": 1,
        "source_sha256": validate_source(slot, source),
    }


def snapshot(backend, sha, slot):
    source = backend.git("show", f"{sha}:{artifact(slot)}", raw=True)
    return {**manifest(slot, source), "source_commit": sha, "source": source}


def propose(backend, base_sha, slot, source, rationale, trace_id, key):
    validate_source(slot, source)
    return backend.propose_content(
        base_sha, artifact(slot), source, {"code_slot": slot}, rationale, trace_id, key
    )


def package_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
