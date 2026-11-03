import pytest

from analyst.config import chat_model, model_ready


@pytest.fixture(autouse=True)
def empty_credentials(monkeypatch):
    for name in ["GIGACHAT_CREDENTIALS", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"]:
        monkeypatch.setenv(name, "")


def test_local_model_does_not_require_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_MODEL", "local-test")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    assert model_ready()
    client = chat_model()
    assert client.model_name == "local-test"
    assert client.openai_api_base == "http://127.0.0.1:11434/v1"


def test_openai_compatible_model_uses_custom_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "provider-model")
    monkeypatch.setenv("LLM_API_KEY", "non-secret-test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    assert model_ready()
    assert chat_model().openai_api_base == "https://example.invalid/v1"


def test_gigachat_native_client_keeps_tls_verification(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gigachat")
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "non-secret-test-credential")
    assert model_ready()
    assert chat_model().verify_ssl_certs is True


def test_local_requires_explicit_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_MODEL", "local-test")
    assert not model_ready()
    with pytest.raises(ValueError, match="Configure"):
        chat_model()


def test_unknown_provider_fails(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "typo")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        model_ready()


def test_repo_path_is_relative_to_core_not_shell_cwd(tmp_path, monkeypatch):
    from analyst.config import CORE_ROOT, evolution_repo

    monkeypatch.setenv("EVOLUTION_REPO_PATH", "../evolution")
    monkeypatch.chdir(tmp_path)
    assert evolution_repo() == CORE_ROOT.parent / "evolution"


def test_evolution_cannot_target_developer_core(monkeypatch):
    from analyst.config import CORE_ROOT, evolution_repo

    monkeypatch.setenv("EVOLUTION_REPO_PATH", str(CORE_ROOT))
    with pytest.raises(ValueError, match="developer core"):
        evolution_repo()


def test_system_env_repo_path_has_priority_over_dotenv(tmp_path, monkeypatch):
    import analyst.config as config

    core = tmp_path / "core"
    core.mkdir()
    (core / ".env").write_text("EVOLUTION_REPO_PATH=../from-dotenv\n")
    external = tmp_path / "from-system-env"
    monkeypatch.setattr(config, "CORE_ROOT", core)
    monkeypatch.setenv("EVOLUTION_REPO_PATH", str(external))
    assert config.evolution_repo() == external


def test_provider_error_does_not_leak_secret(monkeypatch):
    import analyst.graph as module

    monkeypatch.setattr(module, "model_ready", lambda: True)

    def broken(schema, messages):
        raise RuntimeError("credential=DO-NOT-LEAK")

    monkeypatch.setattr(module, "invoke_structured", broken)
    result = module.answer_question("Спрос на нефть?")
    assert result["status"] == "failed"
    assert "DO-NOT-LEAK" not in str(result)


@pytest.mark.parametrize("provider", ["gigachat", "openai"])
@pytest.mark.parametrize("limit", [None, "", "None", "NOne", "1024"])
def test_optional_output_limit(provider, limit, monkeypatch):
    import analyst.config as config

    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", "test")
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "test-only")
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    if limit is None:
        monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
    else:
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", limit)
    client = config.chat_model()
    assert client.max_tokens == (1024 if limit == "1024" else None)
    if limit != "1024":
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content="test")]
        payload = (
            client._build_payload(messages).model_dump(exclude_none=True)
            if provider == "gigachat"
            else client._get_request_payload(messages)
        )
        assert "max_tokens" not in payload and "max_completion_tokens" not in payload


def test_gigachat_structured_schemas_construct_without_network(monkeypatch):
    from analyst.config import structured_model
    from analyst.contracts import CriticVerdict, Route

    monkeypatch.setenv("LLM_PROVIDER", "gigachat")
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "test-only")
    for schema in [Route, CriticVerdict]:
        assert structured_model(schema) is not None


def test_structured_call_preserves_token_usage(monkeypatch):
    from types import SimpleNamespace

    import analyst.config as config
    from analyst.contracts import Route

    parsed = Route(intent="forecast", freshness_required=False)
    usage = {"input_tokens": 12, "output_tokens": 6, "total_tokens": 18}

    class FakeModel:
        def invoke(self, messages):
            return {
                "parsed": parsed,
                "raw": SimpleNamespace(usage_metadata=usage),
                "parsing_error": None,
            }

    monkeypatch.setattr(config, "structured_model", lambda *a, **kw: FakeModel())
    result, measured = config.invoke_structured(Route, [("human", "Brent forecast")])
    assert result == parsed and measured == usage


def test_explicit_hyde_model_is_independent_of_main(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("GIGACHAT_MODEL", "GigaChat-2-Max")
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "test-only")
    client = chat_model(provider="gigachat", model="GigaChat-2")
    assert client.model == "GigaChat-2" and client.verify_ssl_certs is True


def test_openai_model_override_does_not_require_main_model(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    client = chat_model(provider="openai", model="small-model")
    assert client.model_name == "small-model"
