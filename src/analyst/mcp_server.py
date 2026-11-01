"""Two separate HTTP MCP processes, separate bearer credentials."""

import argparse
import hmac
import os
from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.responses import JSONResponse

from analyst.config import CORE_ROOT, evolution_repo, workspace
from analyst.contracts import RetrievalPolicy
from analyst.evolution import Evolution
from analyst.graph import answer_question
from analyst.rag import ReportIndex


def create_server(kind: str, host: str, port: int):
    server = FastMCP(
        f"oilagent-{kind}", host=host, port=port, stateless_http=True, json_response=True
    )
    if kind == "analyst":

        @server.tool()
        def health() -> dict:
            """Report actual prototype capabilities; no model calls or secrets."""
            return {
                "service": "analyst",
                "stage": "report_rag",
                "langgraph": True,
                "rag": (ReportIndex().directory / "index.json").exists(),
                "web": False,
                "forecast": False,
            }

        @server.tool(name="answer_question")
        def answer(question: Annotated[str, Field(min_length=1, max_length=4000)]) -> dict:
            """Call the shared LangGraph core. Missing data is reported explicitly."""
            return answer_question(question)

        @server.tool()
        def search_reports(
            query: Annotated[str, Field(min_length=1, max_length=4000)],
            top_k: Annotated[int, Field(ge=1, le=12)] = 4,
        ) -> list[dict]:
            """Search PDFs locally with source passages, publication dates and PDF pages."""
            return ReportIndex().search(query, top_k=top_k)
    else:
        backend = Evolution(workspace(), repo=evolution_repo())

        @server.tool()
        def propose_change(
            base_sha: str,
            artifact: str,
            policy: Annotated[dict, Field(json_schema_extra=RetrievalPolicy.model_json_schema())],
            rationale: Annotated[str, Field(min_length=1, max_length=2000)],
            trace_id: Annotated[str, Field(max_length=128)],
            idempotency_key: str,
        ) -> dict:
            """Create a policy-only Git candidate. Cannot change code, tests or permissions."""
            return backend.propose(
                base_sha,
                artifact,
                RetrievalPolicy.model_validate(policy),
                rationale,
                trace_id,
                idempotency_key,
            )

        @server.tool()
        def get_diff(candidate_id: str) -> dict:
            """Read exact candidate diff and full SHA fingerprints."""
            return backend.diff(candidate_id)

        @server.tool()
        def run_checks(candidate_id: str) -> dict:
            """Run a fixed synthetic integration check, not a real market quality evaluation."""
            return backend.checks(candidate_id)

        @server.tool()
        def request_review(candidate_id: str) -> dict:
            """Request a separate LLM critic. No configured LLM means REVIEW_BLOCKED."""
            return backend.review(candidate_id)

        @server.tool()
        def get_status(candidate_id: str = "") -> dict:
            """Read candidate status, or trusted baseline when candidate_id is omitted."""
            return backend.load(candidate_id) if candidate_id else backend.baseline()

    return server


class BearerGate:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            provided = headers.get(b"authorization", b"")
            expected = f"Bearer {self.token}".encode()
            if not hmac.compare_digest(provided, expected):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


def main():
    import uvicorn

    load_dotenv(CORE_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["analyst", "evolution"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    token = os.getenv(f"{args.kind.upper()}_MCP_TOKEN", "")
    if len(token) < 24:
        parser.error("Set a distinct MCP token with at least 24 characters in .env")
    port = args.port or (8011 if args.kind == "analyst" else 8012)
    server = create_server(args.kind, args.host, port)
    uvicorn.run(BearerGate(server.streamable_http_app(), token), host=args.host, port=port)


if __name__ == "__main__":
    main()
