"""Optional OpenAI chat-completions facade over Ouroboros's owned Codex model route."""

import hmac
import json
import os
import time
from uuid import uuid4

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Route


def bridge_parameters(body, expected_model):
    if body.get("model") != expected_model or not expected_model.startswith("claudexor::codex="):
        raise ValueError("Select the configured claudexor::codex=<model> route")
    if body.get("stream") or body.get("response_format"):
        raise ValueError("This bridge supports non-streaming function_calling, not response_format")
    if not isinstance(body.get("messages"), list) or not body["messages"]:
        raise ValueError("messages must be a nonempty array")
    limit = body.get("max_completion_tokens", body.get("max_tokens"))
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("Output limit must be a positive integer or omitted")
    return {
        "model": expected_model,
        "messages": body["messages"],
        "tools": body.get("tools"),
        "tool_choice": body.get("tool_choice", "auto"),
        "temperature": body.get("temperature"),
        "max_tokens": limit,
        "wait_for_resources": False,
        "timeout": 120,
    }


def completion_response(model, message, usage):
    route = (usage.get("claudexor") or {}).get("route") or {}
    if route.get("model") and (
        route.get("source") != "codex" or route["model"] != model.split("=", 1)[1]
    ):
        raise ValueError("Owned engine returned a different model route")
    reported = usage.get("reported_tokens")
    measured = reported if isinstance(reported, dict) else usage
    counted = {
        "prompt_tokens": measured.get("prompt_tokens"),
        "completion_tokens": measured.get("completion_tokens"),
    }
    # Omit unavailable counts; never present missing provider metering as zero.
    counted = {k: v for k, v in counted.items() if v is not None}
    if len(counted) == 2:
        counted["total_tokens"] = sum(counted.values())
    if measured.get("cached_tokens") is not None:
        counted["prompt_tokens_details"] = {"cached_tokens": measured["cached_tokens"]}
    return {
        "id": "oilagent-" + uuid4().hex,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
            }
        ],
        **({"usage": counted} if counted else {}),
    }


def endpoint(token, model, chat):
    async def handle(request):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, "Bearer " + token):
            return JSONResponse({"error": {"message": "Unauthorized"}}, status_code=401)
        raw = await request.body()
        if len(raw) > 256000:
            return JSONResponse(
                {"error": {"message": "Input exceeds 256000 bytes"}}, status_code=413
            )
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("JSON object required")
            parameters = bridge_parameters(body, model)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": {"message": str(exc)}}, status_code=400)
        try:
            message, usage = await run_in_threadpool(chat, **parameters)
            return JSONResponse(completion_response(model, message, usage))
        except Exception as exc:
            return JSONResponse(
                {"error": {"message": "Owned Codex model unavailable", "type": type(exc).__name__}},
                status_code=503,
            )

    return handle


def install_model_bridge():
    if os.getenv("OUROBOROS_LLM_BRIDGE_ENABLED", "false").lower() != "true":
        return
    token = os.getenv("LLM_BRIDGE_TOKEN", "")
    if len(token) < 24:
        raise ValueError("Set a private LLM_BRIDGE_TOKEN with at least 24 characters")
    from ouroboros import gateway
    from ouroboros.gateway import router
    from ouroboros.llm import LLMClient

    original = router.collect_routes
    route = Route(
        "/oilagent/v1/chat/completions",
        methods=["POST"],
        endpoint=endpoint(token, os.getenv("LLM_MODEL", ""), LLMClient().chat),
    )

    def collect(*args, **kwargs):
        return [*original(*args, **kwargs), route]

    router.collect_routes = collect
    gateway.collect_routes = collect
