"""Launch the pinned runtime with a narrow native GigaChat schema compatibility adapter."""

import hashlib
import json
import runpy
import sys
from pathlib import Path
from uuid import UUID


def schema_for_gigachat(node):
    if isinstance(node, list):
        return [schema_for_gigachat(value) for value in node]
    if not isinstance(node, dict):
        return node
    variants = node.get("anyOf", [])
    if {v.get("type") for v in variants} == {"object", "string"} and len(variants) == 2:
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
        and schema["function"]["name"] not in on_demand
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


def install_delivery_adapter():
    from ouroboros import agent, loop
    from ouroboros.tools.registry import ToolRegistry
    from ouroboros.tools.tool_result import ToolResult

    original_execute = ToolRegistry.execute_result
    original_loop = loop.run_llm_loop

    def execute(self, name, args):
        allowed = {
            "finish_task",
            "compact_context",
            "list_available_tools",
            "enable_tools",
            "list_skills",
            "read_skill",
        }
        if name not in allowed and not name.startswith(("mcp_analyst__", "mcp_evolution__")):
            return ToolResult(
                status="blocked",
                code="OILAGENT_TOOL_DENIED",
                text="OilAgent permits only analytic MCP, bounded Evolution MCP, "
                "and discovery/completion tools. Shell and file mutation are disabled.",
            )
        if name == "mcp_analyst__answer_question":
            chat_id = getattr(self._ctx, "current_chat_id", None)
            if chat_id is not None:
                session_id = "native-" + hashlib.sha256(str(chat_id).encode()).hexdigest()[:32]
                args = {**args, "session_id": session_id}
        result = original_execute(self, name, args)
        if name == "mcp_analyst__answer_question" and result.status == "ok":
            payload = analyst_result(result.text)
            if payload:
                results = getattr(self._ctx, "_oilagent_results", [])
                results.append(payload)
                self._ctx._oilagent_results = results
        return result

    def run(*args, **kwargs):
        tools = kwargs.get("tools") or args[1]
        tools._ctx._oilagent_results = []
        text, usage, trace = original_loop(*args, **kwargs)
        results = tools._ctx._oilagent_results
        if results:
            trace["canonical_analyst_delivery"] = [r["request_id"] for r in results]
        return canonical_delivery(results, text), usage, trace

    ToolRegistry.execute_result = execute
    loop.run_llm_loop = run
    agent.run_llm_loop = run


if __name__ == "__main__":
    from ouroboros import tool_policy

    initial = tool_policy.initial_tool_schemas

    def initial_with_pins(registry, context_mode="max", schema_names=None):
        names = set(schema_names or ())
        if context_mode == "nano":
            names |= pinned_schema_names(registry)
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
    runpy.run_module("ouroboros.cli", run_name="__main__")
