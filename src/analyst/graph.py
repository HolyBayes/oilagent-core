"""The shared LangGraph boundary. Retrieval/forecast are not implemented yet."""

from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from analyst.config import invoke_structured, model_ready
from analyst.contracts import Route


class State(TypedDict, total=False):
    question: str
    request_id: str
    route: dict | None
    status: str
    answer: str
    warnings: list[str]
    usage: dict


def route(state: State) -> dict:
    if not model_ready():
        return {"route": None, "warnings": ["llm_not_configured"]}
    result, usage = invoke_structured(
        Route,
        [
            (
                "system",
                "Classify an oil/gas analyst request. Do not answer it. "
                "Requests outside this domain are out_of_scope. "
                "Forecasts and supply-cut scenarios use separate intents. "
                "Current news/prices require freshness.",
            ),
            ("human", state["question"]),
        ],
    )
    return {"route": result.model_dump(), "warnings": [], "usage": usage}


def respond(state: State) -> dict:
    if (state.get("route") or {}).get("intent") == "out_of_scope":
        return {"status": "out_of_scope", "answer": "Я отвечаю на вопросы нефтегазового рынка."}
    return {
        "status": "integration_only",
        "answer": "MCP → общий LangGraph core работает. Корпус, web и forecast ещё не подключены; "
        "подтверждённый аналитический ответ пока недоступен.",
    }


builder = StateGraph(State)
builder.add_node("route", route)
builder.add_node("respond", respond)
builder.add_edge(START, "route")
builder.add_edge("route", "respond")
builder.add_edge("respond", END)
graph = builder.compile()


def answer_question(question: str) -> dict:
    state = {"question": question, "request_id": str(uuid4())}
    try:
        return graph.invoke(state)
    except Exception as exc:
        # Provider exception messages can contain credentials or headers.
        return {
            **state,
            "status": "failed",
            "route": None,
            "answer": "Модель недоступна или вернула неподдерживаемый формат.",
            "warnings": [f"model_error:{type(exc).__name__}"],
        }
