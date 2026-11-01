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

    def broken(schema):
        raise RuntimeError("credential=DO-NOT-LEAK")

    monkeypatch.setattr(module, "structured_model", broken)
    result = module.answer_question("Спрос на нефть?")
    assert result["status"] == "failed"
    assert "DO-NOT-LEAK" not in str(result)
