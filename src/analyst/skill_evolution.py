"""Instruction candidates and paired model decisions; evaluation never executes tools."""

import asyncio
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import yaml
from jsonschema import ValidationError, validate

from analyst.config import CORE_ROOT, chat_model, configured_path
from analyst.provider_lock import provider_slot

CAPABILITIES = {"forecast", "rag", "web", "coordinator"}
SEED_CAPABILITIES = {
    "oil_forecast": "forecast",
    "report_rag": "rag",
    "web_research": "web",
    "oilgas_analyst": "coordinator",
}


def skill_path(name):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise ValueError("Invalid skill name")
    return f"ouroboros_skills/{name}/SKILL.md"


def instruction_manifest(name, description, version, instructions):
    skill_path(name)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", version):
        raise ValueError("Skill version must be a string such as 0.1.0")
    metadata = {
        "name": name,
        "description": description,
        "version": version,
        "type": "instruction",
        "os": "any",
        "always_in_context": name == "oilgas_analyst",
    }
    content = (
        "---\n"
        + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        + "---\n\n"
        + instructions
        + "\n"
    )
    validate_skill(skill_path(name), content)
    return content


def validate_skill(artifact, content):
    parts = artifact.split("/")
    if len(parts) != 3 or skill_path(parts[1]) != artifact:
        raise ValueError("Only an instruction SKILL.md may change")
    if not 1 <= len(content.encode()) <= 12000 or not content.startswith("---\n"):
        raise ValueError("Skill must have YAML frontmatter and fit 12000 UTF-8 bytes")
    segments = re.split(r"\n---(?:\n|$)", content[4:], maxsplit=1)
    if len(segments) != 2 or not segments[1].strip():
        raise ValueError("Skill body is required")
    manifest = yaml.safe_load(segments[0])
    allowed = {"name", "description", "version", "type", "always_in_context", "os", "when_to_use"}
    if not isinstance(manifest, dict) or set(manifest) - allowed:
        raise ValueError("Unsupported skill manifest fields; no executable payload or permissions")
    if manifest.get("name") != parts[1] or manifest.get("type") != "instruction":
        raise ValueError("Skill name must match path and type must be instruction")
    for key in ["description", "version"]:
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"Skill {key} is required")
    if manifest.get("os", "any") != "any":
        raise ValueError("Instruction skills must be portable")
    if type(manifest.get("always_in_context", False)) is not bool:
        raise ValueError("always_in_context must be boolean")
    if manifest.get("always_in_context") and parts[1] != "oilgas_analyst":
        raise ValueError("Only the coordinator may be always in context")
    return manifest


def native_instruction_hash(content):
    # Pinned Ouroboros release identity v2 for a single file without dependencies.
    digest = hashlib.sha256(b"ouroboros-skill-release/2\0")
    digest.update(b"SKILL.md\0")
    digest.update(hashlib.sha256(content.encode()).digest())
    return digest.hexdigest()


def validate_skill_tree(backend, state):
    from analyst.code_packages import SLOTS, artifact, validate_source

    directory = state["artifact"].rsplit("/", 1)[0]
    files = backend.git("ls-tree", "-r", "--name-only", state["candidate_sha"], "--", directory)
    allowed = {artifact(slot): slot for slot in SLOTS}
    for path in files.splitlines():
        if path == state["artifact"]:
            continue
        if path not in allowed:
            raise ValueError("Unexpected skill payload")
        source = backend.git("show", f"{state['candidate_sha']}:{path}", raw=True)
        validate_source(allowed[path], source)
        if source != backend.git("show", f"{state['base_sha']}:{path}", raw=True):
            raise ValueError("Instruction candidates cannot change Python")


def committed_content(backend, sha, artifact):
    try:
        return backend.git("show", f"{sha}:{artifact}", raw=True)
    except subprocess.CalledProcessError:
        return ""


def propose_skill(backend, base_sha, name, capability, content, rationale, trace_id, key):
    artifact = skill_path(name)
    validate_skill(artifact, content)
    if capability not in CAPABILITIES:
        raise ValueError("Unknown skill capability")
    if name in SEED_CAPABILITIES and SEED_CAPABILITIES[name] != capability:
        raise ValueError("Capability does not match the existing specialist")
    # Revisions also test all other families, preventing a capability rename from
    # evading cross-skill regressions. Candidate text cannot select evaluator cases.
    return backend.propose_content(
        base_sha,
        artifact,
        content,
        {"skill_name": name, "capability": capability},
        rationale,
        trace_id,
        key,
    )


def eval_path():
    return configured_path("SKILL_EVAL_PATH", "data/skill_eval.json")


def evaluation_identity():
    from analyst.releases import identity

    return {
        **identity(),
        "skill_evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "eval_sha256": hashlib.sha256(eval_path().read_bytes()).hexdigest(),
        "provider": os.getenv("LLM_PROVIDER", "gigachat"),
        "model": (
            os.getenv("GIGACHAT_MODEL", "GigaChat-2")
            if os.getenv("LLM_PROVIDER", "gigachat") == "gigachat"
            else os.getenv("LLM_MODEL", "")
        ),
        "endpoint_sha256": hashlib.sha256(os.getenv("LLM_BASE_URL", "").encode()).hexdigest(),
        "ouroboros_pin_sha256": hashlib.sha256(
            (CORE_ROOT / "config/ouroboros-pin.json").read_bytes()
        ).hexdigest(),
    }


def decision(instructions, case, tools):
    from analyst.budget import current_budget

    messages = [
        (
            "system",
            "Use the supplied instruction skill to choose the next tool. "
            "Do not execute tools. If essential assumptions are absent, ask for them.\n\n"
            + instructions,
        ),
        ("human", case["question"]),
    ]
    budget = current_budget.get()
    with provider_slot():
        if budget:
            budget.reserve_llm([*messages, ("tools", json.dumps(tools))])
        result = chat_model().bind_tools(tools).invoke(messages)
    usage = dict(result.usage_metadata or {})
    if budget:
        budget.account(usage)
    calls = result.tool_calls
    if not calls:
        return {"passed": bool(case.get("clarification")) and bool(result.content), "usage": usage}
    if len(calls) != 1 or case.get("clarification"):
        return {"passed": False, "usage": usage}
    call = calls[0]
    schemas = {t["function"]["name"]: t["function"]["parameters"] for t in tools}
    try:
        validate(call["args"], schemas[call["name"]])
        passed = call["name"] in case["tools"] and all(
            call["args"].get(k) == v for k, v in case.get("arguments", {}).items()
        )
    except (ValidationError, KeyError, TypeError) as exc:
        return {"passed": False, "usage": usage, "error_type": type(exc).__name__}
    return {"passed": passed, "usage": usage, "tool": call["name"], "arguments": call["args"]}


def check_skill(backend, state, decide=None):
    from analyst.code_evaluation import active_id
    from analyst.mcp_server import create_server

    content = backend.git("show", f"{state['candidate_sha']}:{state['artifact']}", raw=True)
    validate_skill(state["artifact"], content)
    validate_skill_tree(backend, state)
    paths = backend.git("diff", "--name-only", state["base_sha"], state["candidate_sha"])
    if (
        paths != state["artifact"]
        or hashlib.sha256(content.encode()).hexdigest() != state["content_sha256"]
    ):
        raise ValueError("Candidate scope/content changed")
    before = committed_content(backend, state["base_sha"], state["artifact"])
    cases = json.loads(eval_path().read_text())
    selected = [c for c in cases if before or c["capability"] == state["capability"]]
    catalog = asyncio.run(create_server("analyst", "127.0.0.1", 0).list_tools())
    tools = [
        {
            "type": "function",
            "function": {
                "name": "mcp_analyst__" + t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in catalog
        if t.name not in {"health", "submit_feedback"}
    ]
    decide = decide or decision
    rows = []
    for case in selected:
        old = decide(before, case, tools) if before else {"passed": False, "usage": {}}
        new = decide(content, case, tools)
        rows.append({"case_id": case["id"], "before": old, "after": new})
    regressions = [r["case_id"] for r in rows if r["before"]["passed"] and not r["after"]["passed"]]
    old_score = sum(r["before"]["passed"] for r in rows)
    new_score = sum(r["after"]["passed"] for r in rows)
    passed = (
        bool(rows)
        and not regressions
        and (new_score > old_score)
        and (bool(before) or new_score == len(rows))
    )
    return {
        "passed": passed,
        "active_release_id": active_id(),
        "scope": "paired model tool choice/arguments; no tool execution or answer-quality claim",
        "new_capability": not bool(before),
        "candidate_sha": state["candidate_sha"],
        "identity": evaluation_identity(),
        "before": old_score,
        "after": new_score,
        "total": len(rows),
        "regressions": regressions,
        "cases": rows,
    }
