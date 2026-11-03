import json

import pytest

from analyst.runtime import isolated_env, private_json, provider_settings, settings_profile


@pytest.mark.parametrize(
    "provider,endpoint,expected",
    [
        ("gigachat", "", "gigachat::GigaChat-2"),
        ("local", "http://127.0.0.1:11434/v1", "openai-compatible::test"),
        ("openai", "https://example.invalid/v1", "openai-compatible::test"),
        ("openai", "", "openai::test"),
    ],
)
def test_native_provider_mapping(provider, endpoint, expected):
    route, _ = provider_settings(
        {"LLM_PROVIDER": provider, "LLM_MODEL": "test", "LLM_BASE_URL": endpoint}
    )
    assert route == expected


def test_native_json_string_settings_and_review_gate(tmp_path):
    profile = settings_profile({}, ["OUROBOROS_MODEL", "OUROBOROS_MODEL_SAFETY"], tmp_path)
    assert profile["OUROBOROS_MODEL"] == profile["OUROBOROS_MODEL_SAFETY"]
    assert json.loads(profile["OUROBOROS_SKILL_SOURCES"])[0]["trust"] == "review"
    rows = json.loads(profile["OUROBOROS_SUBAGENTS"])["items"]
    assert sum(r["review_eligible"] for r in rows) == 1
    assert len(rows) == 4
    assert profile["OUROBOROS_SUBAGENTS_MODE"] == "auto"
    assert profile["OUROBOROS_MAX_SUBAGENT_DEPTH"] == 1
    assert profile["OUROBOROS_REVIEW_ENFORCEMENT"] == "blocking"
    assert profile["OUROBOROS_AUTO_GRANT_REVIEWED_SKILLS"] == "false"
    assert profile["OUROBOROS_MODEL_FALLBACKS"] == ""
    assert profile["OUROBOROS_MAX_ROUNDS"] == 8
    analyst, evolution = profile["MCP_SERVERS"]
    assert analyst["schemas_at_start"] and {
        "answer_question",
        "forecast",
        "search_reports",
        "search_web_sources",
    } <= set(analyst["allowed_tools"])
    assert not evolution["schemas_at_start"]


def test_runtime_env_does_not_inherit_unrelated_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "not-for-runtime")
    monkeypatch.setenv("OPENAI_API_KEY", "not-for-runtime")
    monkeypatch.setenv("GIGACHAT_CREDENTIALS", "not-for-runtime")
    env = isolated_env(tmp_path, tmp_path / "repo")
    assert not {"GITHUB_TOKEN", "OPENAI_API_KEY", "GIGACHAT_CREDENTIALS"} & env.keys()
    assert env["OUROBOROS_DATA_DIR"] == str(tmp_path / "data")


def test_runtime_settings_are_private(tmp_path):
    path = tmp_path / "settings.json"
    private_json(path, {"secret": "test-only"})
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("configured,expected", [(None, "1"), ("2", "2")])
def test_native_profile_preserves_explicit_review_cycle_limit(tmp_path, configured, expected):
    env = {} if configured is None else {"OUROBOROS_REVIEW_MAX_CYCLES": configured}
    assert settings_profile(env, [], tmp_path)["OUROBOROS_REVIEW_MAX_CYCLES"] == expected
