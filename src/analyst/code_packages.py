"""Versioned capability source packages; no host imports or automatic activation."""

import ast
import hashlib
import json
import re

SLOTS = {
    "forecast": "oil_forecast",
    "scenario": "oil_forecast",
    "chunking": "report_rag",
    "reranking": "report_rag",
    "query_strategy": "report_rag",
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
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run"]
    if len(functions) != 1:
        raise ValueError("Capability must export run(request)")
    args = functions[0].args
    if len(args.posonlyargs + args.args) != 1 or args.vararg or args.kwarg or args.kwonlyargs:
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
    skill = f"ouroboros_skills/{SLOTS[slot]}/SKILL.md"
    old = backend.git("show", f"{base_sha}:{skill}", raw=True)
    match = re.search(r"(?m)^version: (\d+)\.(\d+)\.(\d+)[ \t]*$", old)
    if not match:
        raise ValueError("Existing skill must have a semantic version")
    version = f"version: {match[1]}.{match[2]}.{int(match[3]) + 1}"
    updated = old[: match.start()] + version + old[match.end() :]
    return backend.propose_content(
        base_sha,
        artifact(slot),
        source,
        {"code_slot": slot, "package_updates": {skill: updated}},
        rationale,
        trace_id,
        key,
    )


def package_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def seed_source(slot):
    from analyst.config import CORE_ROOT

    artifact(slot)
    return (CORE_ROOT / "src/analyst/seeds/implementations" / (slot + ".py")).read_text()


def repository_files(backend, sha):
    """Capture the entire skill tree from Git, never the mutable working copy."""
    names = backend.git("ls-tree", "-r", "--name-only", sha, "--", "ouroboros_skills").splitlines()
    if len(names) > 100:
        raise ValueError("Skill package exceeds 100 files")
    files = {name: backend.git("show", f"{sha}:{name}", raw=True) for name in names}
    if sum(len(v.encode()) for v in files.values()) > 512000:
        raise ValueError("Skill package exceeds 512000 bytes")
    return files


def query_strategy_extension(files):
    """Exact operator migration from a five-method package; never a candidate bypass."""
    if artifact("query_strategy") in files:
        raise ValueError("Query strategy already exists")
    result = dict(files)
    result[artifact("query_strategy")] = seed_source("query_strategy")
    path = "ouroboros_skills/report_rag/SKILL.md"
    old = result[path]
    match = re.search(r"(?m)^version: (\d+)\.(\d+)\.(\d+)[ \t]*$", old)
    if not match:
        raise ValueError("Existing skill version required")
    result[path] = (
        old[: match.start()]
        + (f"version: {match[1]}.{match[2]}.{int(match[3]) + 1}")
        + old[match.end() :]
    )
    result[path] += (
        "\nquery_strategy.py owns search expansion and result fusion. Its run(request) phases: "
        "plan returns a prompt (empty skips LLM), expand returns bounded searches/probes/weights, "
        "fuse returns a permutation of candidate indices. Core owns model calls, caches, "
        "budgets, embeddings and evidence. Read this slot before proposing "
        "HyDE/MultiQuery changes. "
        "Fixed evaluation replays approved Lite probes; changed prompts/models need matching "
        "operator-owned fixtures and are otherwise unavailable, never silently scored.\n"
    )
    coordinator = "ouroboros_skills/oilgas_analyst/SKILL.md"
    old = result[coordinator]
    match = re.search(r"(?m)^version: (\d+)\.(\d+)\.(\d+)[ \t]*$", old)
    if not match:
        raise ValueError("Existing coordinator version required")
    updated = (
        old[: match.start()]
        + (f"version: {match[1]}.{match[2]}.{int(match[3]) + 1}")
        + old[match.end() :]
    )
    marker = "scenario, chunking, reranking and search_strategy."
    result[coordinator] = (
        updated.replace(
            marker, "scenario, chunking, reranking, query_strategy and search_strategy."
        )
        if marker in updated
        else updated + "\nquery_strategy is the report_rag search expansion/fusion slot.\n"
    )
    return result
