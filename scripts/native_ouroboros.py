"""Launch the pinned runtime with a narrow native GigaChat schema compatibility adapter."""

import runpy


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
    runpy.run_module("ouroboros.cli", run_name="__main__")
