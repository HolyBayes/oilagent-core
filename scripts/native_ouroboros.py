"""Launch the pinned runtime with a narrow native GigaChat schema compatibility adapter."""

import hashlib
import json
import re
import runpy
import sys
from pathlib import Path
from uuid import UUID

DISCOVERY_TOOLS = {
    "finish_task",
    "compact_context",
    "list_available_tools",
    "enable_tools",
    "list_skills",
    "read_skill",
    "read_file",
}
DELEGATION_TOOLS = {"schedule_subagent", "get_task_result", "wait_task", "wait_tasks"}
SPECIALISTS = {"report-analyst", "web-analyst", "forecast-analyst"}


def tool_allowed(name, args, *, child=False):
    if name == "read_file":
        return args.get("root") == "skill_payload" and args.get("path") == "SKILL.md"
    if name in DISCOVERY_TOOLS:
        return True
    if name in DELEGATION_TOOLS:
        if child:
            return False
        if name == "schedule_subagent":
            actor = args.get("subagent_id", "")
            selected = actor.split("~")[-1] if isinstance(actor, str) else ""
            return (
                selected in SPECIALISTS
                and args.get("write_surface", "read_only") == "read_only"
                and not args.get("may_mutate", False)
            )
        return True
    if name.startswith("mcp_analyst__"):
        return not (child and name == "mcp_analyst__submit_feedback")
    return name.startswith("mcp_evolution__") and not child


def schema_for_gigachat(node):
    if isinstance(node, list):
        return [schema_for_gigachat(value) for value in node]
    if not isinstance(node, dict):
        return node
    types = node.get("type")
    if isinstance(types, list) and len([t for t in types if t != "null"]) == 1:
        node = {**node, "type": next(t for t in types if t != "null")}
    for union in ["anyOf", "oneOf"]:
        variants = node.get(union, [])
        non_null = [v for v in variants if v.get("type") != "null"]
        if len(variants) == 2 and len(non_null) == 1:
            node = {**{k: v for k, v in node.items() if k != union}, **non_null[0]}
    variants = node.get("anyOf", [])
    if (
        len(variants) == 2
        and all(isinstance(v.get("type"), str) for v in variants)
        and {v.get("type") for v in variants} == {"object", "string"}
    ):
        # Advertise the existing string-reference alternative; host validation is unchanged.
        node = {
            **{k: v for k, v in node.items() if k != "anyOf"},
            **next(v for v in variants if v.get("type") == "string"),
        }
    return {key: schema_for_gigachat(value) for key, value in node.items()}


def pinned_schema_names(registry):
    on_demand = getattr(registry, "on_demand_schema_names", lambda: frozenset())()
    return {
        schema["function"]["name"]
        for schema in registry.schemas()
        if schema["function"]["name"].startswith("mcp_")
        and (
            schema["function"]["name"] not in on_demand
            or schema["function"]["name"]
            in {"mcp_analyst__answer_question", "mcp_analyst__forecast"}
        )
    }


def analyst_result(text):
    decoder = json.JSONDecoder()
    for offset, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[offset:])
            if isinstance(value, dict) and isinstance(value.get("answer"), str):
                UUID(value["request_id"])
                if isinstance(value.get("status"), str):
                    return value
        except (ValueError, KeyError, TypeError):
            continue
    return None


def canonical_delivery(results, model_text):
    if not results:
        return model_text
    return "\n\n---\n\n".join(
        r["answer"] + f"\n\nЗапрос: `{r['request_id']}`; статус: `{r['status']}`." for r in results
    )


def delivery_file(ctx, task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{8,32}", task_id):
        return None
    from ouroboros.tool_access_paths import canonical_data_root

    return canonical_data_root(ctx) / "state/oilagent-deliveries" / f"{task_id}.json"


def save_delivery(ctx, results, text):
    path = delivery_file(ctx, getattr(ctx, "task_id", None))
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "answer_sha256": hashlib.sha256(text.strip().encode()).hexdigest(),
        "results": results,
    }
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False))
    temp.chmod(0o600)
    temp.replace(path)


def joined_delivery(ctx, child_id):
    if not delivery_file(ctx, getattr(ctx, "task_id", None)):
        return []
    path = delivery_file(ctx, child_id)
    if not path or not path.exists():
        return []
    from ouroboros.task_status import load_effective_task_result
    from ouroboros.tool_access_paths import canonical_data_root

    child = load_effective_task_result(
        canonical_data_root(ctx), child_id, materialize_artifacts=False
    )
    if (
        child.get("parent_task_id") != getattr(ctx, "task_id", None)
        or child.get("status") != "completed"
        or child.get("delegation_role") != "subagent"
    ):
        return []
    receipt = json.loads(path.read_text())
    if (
        receipt["answer_sha256"]
        != hashlib.sha256(child.get("result", "").strip().encode()).hexdigest()
    ):
        return []
    return receipt["results"]


def final_delivery(ctx, results, model_text):
    mixed = False
    task_path = delivery_file(ctx, getattr(ctx, "task_id", None))
    if task_path:
        from ouroboros.task_store import task_facts
        from ouroboros.tool_access_paths import canonical_data_root

        children = task_facts(
            canonical_data_root(ctx),
            where="parent_task_id=? AND delegation_role='subagent'",
            params=(ctx.task_id,),
        )
        # A parked/resumed parent gets a fresh context; durable child facts and
        # host receipts, rather than process-local counters, determine its join.
        existing = {r["request_id"] for r in results}
        for task_id in children:
            rows = joined_delivery(ctx, task_id)
            if rows:
                results.extend(r for r in rows if r["request_id"] not in existing)
                existing.update(r["request_id"] for r in rows)
                ctx._oilagent_joined.add(task_id)
        mixed = bool(children) and (
            bool(set(children) - ctx._oilagent_joined) or task_path.with_suffix(".raw").exists()
        )
    if not results:
        return model_text
    delivered = canonical_delivery(results, model_text)
    if mixed:
        return model_text + "\n\nРасчётные результаты дочерних задач:\n\n" + delivered
    if results:
        save_delivery(ctx, results, delivered)
    return delivered


def install_delivery_adapter():
    from ouroboros import agent, loop
    from ouroboros.tools.registry import ToolRegistry
    from ouroboros.tools.tool_result import ToolResult

    original_execute = ToolRegistry.execute_result
    original_loop = loop.run_llm_loop
    original_schemas = getattr(ToolRegistry, "schemas", None)

    if original_schemas:

        def schemas(self, *args, **kwargs):
            child = self._is_local_readonly_subagent()
            names = DISCOVERY_TOOLS | (set() if child else DELEGATION_TOOLS)
            return [
                s
                for s in original_schemas(self, *args, **kwargs)
                if s["function"]["name"] in names
                or tool_allowed(s["function"]["name"], {}, child=child)
            ]

        ToolRegistry.schemas = schemas

    def execute(self, name, args):
        child = getattr(self, "_is_local_readonly_subagent", lambda: False)()
        if not tool_allowed(name, args, child=child):
            return ToolResult(
                status="blocked",
                code="OILAGENT_TOOL_DENIED",
                text="OilAgent permits analytic MCP, bounded skill/policy candidates, "
                "skill manifest reads and read-only specialist delegation. "
                "Children cannot mutate Evolution; shell/file writes are disabled.",
            )
        from analyst.capabilities import CapabilityDisabled, require_skill, tool_owner

        try:
            if name.startswith(("mcp_analyst__", "mcp_evolution__")):
                kind, method = name.removeprefix("mcp_").split("__", 1)
                owner = tool_owner(kind, method)
                if owner:
                    require_skill(owner)
            if name == "schedule_subagent":
                actor = args.get("subagent_id", "").split("~")[-1]
                require_skill(tool_owner("specialists", actor))
        except CapabilityDisabled as exc:
            return ToolResult(status="blocked", code="MODULE_DISABLED", text=str(exc))
        if name == "mcp_analyst__answer_question":
            chat_id = getattr(self._ctx, "current_chat_id", None)
            if chat_id is not None:
                session_id = "native-" + hashlib.sha256(str(chat_id).encode()).hexdigest()[:32]
                args = {**args, "session_id": session_id}
        result = original_execute(self, name, args)
        if name.startswith(("mcp_analyst__", "mcp_evolution__")) and result.status == "ok":
            self._ctx._oilagent_tool_observed = True
            if name.startswith("mcp_evolution__"):
                self._ctx._oilagent_evolution_observed = True
        if name.startswith("mcp_analyst__") and result.status == "ok":
            payload = analyst_result(result.text)
            if payload:
                results = getattr(self._ctx, "_oilagent_results", [])
                results.append(payload)
                self._ctx._oilagent_results = results
            else:
                path = delivery_file(self._ctx, getattr(self._ctx, "task_id", None))
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.with_suffix(".raw").touch(mode=0o600)
        if name in {"get_task_result", "wait_task", "wait_tasks"} and result.status == "ok":
            ids = args.get("task_ids", []) if name == "wait_tasks" else [args.get("task_id")]
            for task_id in ids:
                rows = joined_delivery(self._ctx, task_id)
                if rows:
                    existing = {r["request_id"] for r in self._ctx._oilagent_results}
                    self._ctx._oilagent_results.extend(
                        r for r in rows if r["request_id"] not in existing
                    )
                    self._ctx._oilagent_joined.add(task_id)
        return result

    def run(*args, **kwargs):
        tools = kwargs.get("tools") or args[1]
        tools._ctx._oilagent_results = []
        tools._ctx._oilagent_joined = set()
        tools._ctx._oilagent_tool_observed = False
        tools._ctx._oilagent_evolution_observed = False
        text, usage, trace = original_loop(*args, **kwargs)
        results = tools._ctx._oilagent_results
        if not results and not tools._ctx._oilagent_evolution_observed:
            from ouroboros.task_status import load_effective_task_result
            from ouroboros.tool_access_paths import canonical_data_root

            task = load_effective_task_result(
                canonical_data_root(tools._ctx), tools._ctx.task_id, materialize_artifacts=False
            )
            question = task.get("description", "")
            if isinstance(question, str) and 1 <= len(question) <= 4000:
                execute(tools, "mcp_analyst__answer_question", {"question": question})
                results = tools._ctx._oilagent_results
                trace["oilagent_report_first_fallback"] = bool(results)
        delivered = final_delivery(tools._ctx, results, text)
        if not results and not tools._ctx._oilagent_evolution_observed:
            delivered = (
                "Не удалось подтвердить ответ по источникам. Непроверенные цифры не приводятся."
            )
            trace["oilagent_unverified_delivery_blocked"] = True
        if results:
            trace["canonical_analyst_delivery"] = [r["request_id"] for r in results]
            trace["canonical_child_deliveries"] = sorted(tools._ctx._oilagent_joined)
        return delivered, usage, trace

    ToolRegistry.execute_result = execute
    loop.run_llm_loop = run
    agent.run_llm_loop = run


def configure_runtime():
    from ouroboros.tools.registry import ToolRegistry

    if getattr(ToolRegistry, "_oilagent_adapted", False):
        return
    ToolRegistry._oilagent_adapted = True
    from ouroboros import tool_policy

    initial = tool_policy.initial_tool_schemas

    def initial_with_pins(registry, context_mode="max", schema_names=None):
        names = set(schema_names or ())
        if context_mode == "nano":
            names |= pinned_schema_names(registry)
            available = {s["function"]["name"] for s in registry.schemas()}
            names |= available & {
                "schedule_subagent",
                "wait_tasks",
                "get_task_result",
                "list_skills",
                "read_file",
                "finish_task",
            }
        return initial(registry, context_mode=context_mode, schema_names=sorted(names))

    tool_policy.initial_tool_schemas = initial_with_pins
    from ouroboros.llm import LLMClient

    original = LLMClient._gigachat_functions
    LLMClient._gigachat_functions = staticmethod(lambda tools: schema_for_gigachat(original(tools)))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from analyst.provider_lock import provider_slot

    original_gigachat = LLMClient._chat_gigachat

    def serialized_gigachat(self, *args, **kwargs):
        with provider_slot():
            return original_gigachat(self, *args, **kwargs)

    LLMClient._chat_gigachat = serialized_gigachat
    install_delivery_adapter()
    # Spawn/forkserver workers import their target afresh; parent monkeypatches
    # alone do not reach native delegated sessions.
    from native_worker import worker_main
    from supervisor import worker_process

    worker_process._oilagent_original_worker_main = worker_process.worker_main
    worker_process.worker_main = worker_main
    from native_bridge import install_model_bridge

    install_model_bridge()


if __name__ == "__main__":
    configure_runtime()
    runpy.run_module("ouroboros.cli", run_name="__main__")
