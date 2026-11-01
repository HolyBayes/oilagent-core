import os
from pathlib import Path

from dotenv import load_dotenv

CORE_ROOT = Path(os.getenv("OILAGENT_CORE_ROOT", Path(__file__).resolve().parents[2])).resolve()


def configured_path(name: str, default: str) -> Path:
    load_dotenv(CORE_ROOT / ".env", override=False)
    path = Path(os.getenv(name, default))
    return (path if path.is_absolute() else CORE_ROOT / path).resolve()


def workspace() -> Path:
    return configured_path("WORKSPACE_PATH", "workspace/runtime")


def evolution_repo() -> Path:
    path = configured_path("EVOLUTION_REPO_PATH", "../evolution")
    if path == CORE_ROOT:
        raise ValueError("Evolution repository must not be the developer core repository")
    return path


def model_ready():
    load_dotenv(CORE_ROOT / ".env", override=False)
    provider = os.getenv("LLM_PROVIDER", "gigachat")
    if provider == "gigachat":
        return bool(os.getenv("GIGACHAT_CREDENTIALS"))
    if provider == "local":
        return bool(os.getenv("LLM_MODEL") and os.getenv("LLM_BASE_URL"))
    if provider == "openai":
        return bool(os.getenv("LLM_MODEL") and os.getenv("LLM_API_KEY"))
    raise ValueError("LLM_PROVIDER must be gigachat, openai or local")


def chat_model():
    load_dotenv(CORE_ROOT / ".env", override=False)
    raw_limit = os.getenv("LLM_MAX_OUTPUT_TOKENS", "").strip()
    output_limit = None if raw_limit.lower() in {"", "none"} else int(raw_limit)
    if output_limit is not None and output_limit <= 0:
        raise ValueError("LLM_MAX_OUTPUT_TOKENS must be a positive integer or None")
    output_options = {} if output_limit is None else {"max_tokens": output_limit}
    if os.getenv("LLM_PROVIDER", "gigachat") == "gigachat":
        from langchain_gigachat import GigaChat

        if not model_ready():
            raise ValueError("Configure GIGACHAT_CREDENTIALS in local .env")
        return GigaChat(
            model=os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max"),
            credentials=os.environ["GIGACHAT_CREDENTIALS"],
            scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            ca_bundle_file=os.getenv("GIGACHAT_CA_BUNDLE_FILE") or None,
            verify_ssl_certs=True,
            temperature=0,
            **output_options,
            timeout=float(os.getenv("LLM_TIMEOUT_SEC", "20")),
            max_retries=0,
        )
    from langchain_openai import ChatOpenAI

    model, key = os.getenv("LLM_MODEL"), os.getenv("LLM_API_KEY")
    if not model_ready():
        raise ValueError("Configure model and credentials or local endpoint in .env")
    return ChatOpenAI(
        model=model,
        api_key=key or "local-no-auth",
        base_url=os.getenv("LLM_BASE_URL") or None,
        temperature=0,
        **output_options,
        timeout=float(os.getenv("LLM_TIMEOUT_SEC", "20")),
        max_retries=0,
    )


def structured_model(schema, *, include_raw=False):
    method = os.getenv("LLM_STRUCTURED_METHOD", "function_calling")
    if method not in {"function_calling", "json_schema", "json_mode"}:
        raise ValueError("Unsupported LLM_STRUCTURED_METHOD")
    return chat_model().with_structured_output(schema, method=method, include_raw=include_raw)


def invoke_structured(schema, messages):
    """Keep provider-reported token counts; bound input size without another API call."""
    if sum(len(text) for _, text in messages) > 12000:
        raise ValueError("Structured request exceeds 12000 characters")
    result = structured_model(schema, include_raw=True).invoke(messages)
    if result["parsed"] is None or result.get("parsing_error"):
        raise ValueError("Model response does not satisfy the schema")
    return result["parsed"], dict(result["raw"].usage_metadata or {})
