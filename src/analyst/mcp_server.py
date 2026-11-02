"""Two separate HTTP MCP processes, separate bearer credentials."""

import argparse
import hmac
import json
import os
from typing import Annotated
from uuid import UUID, uuid4

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from starlette.responses import JSONResponse

from analyst.config import CORE_ROOT, configured_path, evolution_repo, workspace
from analyst.contracts import RetrievalPolicy
from analyst.evolution import Evolution
from analyst.forecast import forecast_brent, render_forecast
from analyst.graph import answer_question
from analyst.quotes import latest_quote
from analyst.rag import ReportIndex
from analyst.releases import active_release
from analyst.scenario import SupplyScenario, supply_cut_scenario
from analyst.traces import record_feedback, save_trace
from analyst.web import search_web, web_enabled


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
                "web": web_enabled(),
                "forecast": True,
            }

        @server.tool(name="answer_question")
        def answer(
            question: Annotated[str, Field(min_length=1, max_length=4000)], session_id: str = ""
        ) -> dict:
            """Answer oil/gas questions using loaded OPEC/EIA reports and web sources.

            Calculate new Brent forecasts with ARIMA and ETS from prepared EIA history.
            Reports and price data are already loaded; no user upload is required.
            Returns the answer with sources, prediction intervals and limitations.
            """
            return answer_question(question, session_id)

        @server.tool(name="forecast")
        def forecast_prices(
            asset: Annotated[str, Field(min_length=1, max_length=32)],
            horizon_months: Annotated[int, Field(ge=1, le=6)] = 3,
            as_of: str = "",
            start_date: str = "",
            end_date: str = "",
        ) -> dict:
            """Calculate ARIMA/ETS forecasts, 80% prediction intervals and backtest.

            asset: brent (only supported asset; other names are rejected).

            start_date/end_date: inclusive ISO dates of daily history, default last 120
            completed months. Reuse cached history; download only uncovered intervals.
            as_of: calculation cutoff, no later than today. Horizon is in months.
            """
            if asset.casefold() != "brent":
                raise ValueError("Unsupported forecast asset; currently supported: brent")
            request_id = str(uuid4())
            try:
                result = forecast_brent(horizon_months, as_of, start_date, end_date)
                result = {
                    **result,
                    "asset": "brent",
                    "answer": render_forecast(result),
                    "request_id": request_id,
                    "status": "forecasted" if result["data_cache"]["complete"] else "partial",
                }
            except Exception as exc:
                result = {
                    "asset": "brent",
                    "request_id": request_id,
                    "status": "forecast_unavailable",
                    "answer": "Прогноз недоступен: " + type(exc).__name__,
                }
            save_trace(
                {
                    **result,
                    "tool": "forecast",
                    "arguments": dict(
                        asset="brent",
                        horizon_months=horizon_months,
                        as_of=as_of,
                        start_date=start_date,
                        end_date=end_date,
                    ),
                }
            )
            return result

        @server.tool()
        def supply_cut(
            inputs: Annotated[dict, Field(json_schema_extra=SupplyScenario.model_json_schema())],
        ) -> dict:
            """Conditional supply-cut sensitivity from explicit user assumptions, not ARIMA."""
            return supply_cut_scenario(inputs)

        @server.tool()
        def submit_feedback(
            request_id: str,
            rating: Annotated[int, Field(ge=-1, le=1)],
            comment: Annotated[str, Field(min_length=1, max_length=2000)],
        ) -> dict:
            """Store user feedback about a request; never treat it as verified market evidence."""
            return record_feedback(request_id, rating, comment)

        @server.tool()
        def market_quote(instrument: str = "Brent") -> dict:
            """Latest delayed Brent/WTI futures quote, timestamp and explicit price type."""
            return latest_quote(instrument)

        @server.tool()
        def search_web_sources(
            query: Annotated[str, Field(min_length=1, max_length=4000)],
            freshness: bool = True,
        ) -> dict:
            """Search trusted web sources without an API key. Snippets are not live price feeds."""
            return search_web(query, freshness=freshness)

        @server.tool()
        def search_reports(
            query: Annotated[str, Field(min_length=1, max_length=4000)],
            top_k: Annotated[int, Field(ge=1, le=12)] = 4,
        ) -> list[dict]:
            """Search PDFs locally with source passages, publication dates and PDF pages."""
            return ReportIndex().search(query, top_k=top_k)
    else:
        backend = Evolution(workspace(), repo=evolution_repo())

        def require_trace(trace_id):
            request_id = str(UUID(trace_id))
            trace_path = configured_path("TRACE_PATH", "workspace/traces") / f"{request_id}.json"
            if not trace_path.exists():
                raise ValueError("A recorded failure/request trace is required")
            if json.loads(trace_path.read_text()).get("request_id") != request_id:
                raise ValueError("Trace identity mismatch")

        @server.tool()
        def read_skill(name: str) -> dict:
            """Read a committed instruction skill from trusted main, never from a candidate."""
            from analyst.skill_evolution import skill_path

            sha = backend.baseline()["base_sha"]
            return {"base_sha": sha, "content": backend.git("show", f"{sha}:{skill_path(name)}")}

        @server.tool()
        def propose_skill(
            base_sha: str,
            name: str,
            capability: str,
            description: Annotated[str, Field(min_length=1, max_length=500)],
            version: Annotated[str, Field(min_length=1, max_length=64)],
            instructions: Annotated[str, Field(min_length=1, max_length=10000)],
            rationale: Annotated[str, Field(min_length=1, max_length=2000)],
            trace_id: str,
            idempotency_key: str,
        ) -> dict:
            """Create/revise an instruction-only skill Git candidate; never install or enable it.

            capability: forecast, rag, web or coordinator. version: semver string, e.g. 0.1.0.
            instructions: Markdown body only. Backend writes validated YAML metadata.
            run_checks for skills makes paid paired model tool-selection evaluations.
            Native review and operator stage/enable are separate, required actions.
            """
            from analyst.skill_evolution import instruction_manifest
            from analyst.skill_evolution import propose_skill as propose

            require_trace(trace_id)
            return propose(
                backend,
                base_sha,
                name,
                capability,
                instruction_manifest(name, description, version, instructions),
                rationale,
                trace_id,
                idempotency_key,
            )

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
            require_trace(trace_id)
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
            """Policy: fixed PDF checks, no LLM. Skill: paid paired tool-selection evaluation.

            Both require improvement and no regressions; no installation or release occurs.
            """
            return backend.checks(candidate_id, real=True)

        @server.tool()
        def request_review(candidate_id: str) -> dict:
            """Request a separate LLM critic. No configured LLM means REVIEW_BLOCKED."""
            return backend.review(candidate_id)

        @server.tool()
        def get_status(candidate_id: str = "") -> dict:
            """Read candidate status, or trusted baseline when candidate_id is omitted."""
            if candidate_id:
                return backend.load(candidate_id)
            return {**backend.baseline(), "serving": active_release()}

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
