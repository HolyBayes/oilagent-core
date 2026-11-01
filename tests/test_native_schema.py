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
