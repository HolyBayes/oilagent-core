import runpy
from pathlib import Path
from types import SimpleNamespace

normalize = runpy.run_path(str(Path(__file__).parents[1] / "scripts/native_ouroboros.py"))[
    "schema_for_gigachat"
]
pinned = runpy.run_path(str(Path(__file__).parents[1] / "scripts/native_ouroboros.py"))[
    "pinned_schema_names"
]


def test_only_existing_string_alternative_is_advertised():
    original = {
        "properties": {
            "binding": {
                "description": "exact decision ref",
                "anyOf": [{"type": "object"}, {"type": "string", "minLength": 1}],
            }
        },
        "additionalProperties": False,
        "required": ["binding"],
    }
    converted = normalize(original)
    assert converted["properties"]["binding"] == {
        "description": "exact decision ref",
        "type": "string",
        "minLength": 1,
    }
    assert converted["additionalProperties"] is False and converted["required"] == ["binding"]
    assert "anyOf" in original["properties"]["binding"]


def test_other_unions_and_validation_constraints_are_preserved():
    schema = {
        "anyOf": [{"type": "integer", "minimum": 1}, {"type": "string"}],
        "oneOf": [{"const": "a"}, {"const": "b"}],
    }
    assert normalize(schema) == schema


def test_pin_only_selects_currently_permitted_non_demand_mcp_schemas():
    registry = SimpleNamespace(
        schemas=lambda: [
            {"function": {"name": n}}
            for n in [
                "compact_context",
                "mcp_analyst__answer_question",
                "mcp_evolution__get_status",
            ]
        ],
        on_demand_schema_names=lambda: {"mcp_evolution__get_status"},
    )
    assert pinned(registry) == {"mcp_analyst__answer_question"}
    registry.schemas = lambda: []
    assert pinned(registry) == set()


def test_canonical_delivery_does_not_rewrite_sources_or_tables():
    functions = runpy.run_path(str(Path(__file__).parents[1] / "scripts/native_ouroboros.py"))
    result = {
        "request_id": "b4c29b09-a359-45e4-b268-384d7042302c",
        "status": "forecasted",
        "answer": "Исторический дневной ряд [F1]\n| ARIMA | 70 |",
    }
    import json

    assert functions["analyst_result"]("structuredContent: " + json.dumps(result)) == result
    delivered = functions["canonical_delivery"]([result], "Неверный ежемесячный отчёт")
    assert result["answer"] in delivered and "ежемесячный" not in delivered
    assert result["request_id"] in delivered
    assert functions["canonical_delivery"]([], "no tool result") == "no tool result"
