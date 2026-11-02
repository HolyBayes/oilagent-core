"""Isolated, pinned Ouroboros launch profile; secrets never enter tracked files."""

import json
import os
import subprocess
import sys

from dotenv import load_dotenv

from analyst.config import CORE_ROOT, configured_path, evolution_repo


def provider_settings(env):
    provider = env.get("LLM_PROVIDER", "gigachat")
    if provider == "gigachat":
        return f"gigachat::{env.get('GIGACHAT_MODEL') or 'GigaChat-2'}", {
            "GIGACHAT_CREDENTIALS": env.get("GIGACHAT_CREDENTIALS", ""),
            "GIGACHAT_SCOPE": env.get("GIGACHAT_SCOPE") or "GIGACHAT_API_PERS",
            "GIGACHAT_VERIFY_SSL_CERTS": "true",
            "OUROBOROS_EXTRA_CA_BUNDLE": env.get("GIGACHAT_CA_BUNDLE_FILE", ""),
        }
    if provider not in {"local", "openai"}:
        raise ValueError("Unsupported LLM_PROVIDER")
    model, url = env.get("LLM_MODEL", ""), env.get("LLM_BASE_URL", "")
    if not model or (provider == "local" and not url):
        raise ValueError("Configure LLM_MODEL and the local endpoint")
    if provider == "local" and model.startswith("claudexor::codex="):
        return model, {}
    if url:
        return f"openai-compatible::{model}", {
            "OPENAI_COMPATIBLE_BASE_URL": url,
            "OPENAI_COMPATIBLE_API_KEY": env.get("LLM_API_KEY", ""),
        }
    return f"openai::{model}", {"OPENAI_API_KEY": env.get("LLM_API_KEY", "")}


def settings_profile(env, model_keys, skill_source):
    route, credentials = provider_settings(env)
    profile = {key: route for key in model_keys}
    profile.update(credentials)
    profile.update(
        {
            "OUROBOROS_MODEL_FALLBACKS": "",
            "OUROBOROS_MODEL_FALLBACK": "",
            "OUROBOROS_MODEL_HEAVY": route,
            "OUROBOROS_RUNTIME_MODE": "light",
            "OUROBOROS_CONTEXT_MODE": "nano",
            "OUROBOROS_CONTEXT_MODE_AUTO_LOW": "false",
            "OUROBOROS_REVIEW_ENFORCEMENT": "blocking",
            "OUROBOROS_AUTO_GRANT_REVIEWED_SKILLS": "false",
            "OUROBOROS_SUBAGENTS_MODE": "auto",
            "OUROBOROS_MAX_ACTIVE_SUBAGENTS_PER_ROOT": 2,
            "OUROBOROS_MAX_SUBAGENT_DEPTH": 1,
            "OUROBOROS_ALLOW_MUTATIVE_SUBAGENTS": "false",
            "OUROBOROS_MAX_WORKERS": 3,
            "OUROBOROS_MAX_ROUNDS": 8,
            "OUROBOROS_TASK_ABS_CEILING_SEC": 300,
            "OUROBOROS_REVIEW_MAX_CYCLES": "1",
            "TOTAL_BUDGET": 2.0,
            "OUROBOROS_PER_TASK_COST_USD": 0.5,
            "OUROBOROS_POST_TASK_EVOLUTION": "false",
            "OUROBOROS_STARTER_SKILLS": [],
            "OUROBOROS_SKILL_SOURCES": [
                {
                    "id": "oilagent",
                    "name": "OilAgent local skills",
                    "kind": "local",
                    "path": str(skill_source),
                    "trust": "review",
                    "confirmed": True,
                }
            ],
            "OUROBOROS_SUBAGENTS": {
                "enabled": True,
                "items": [
                    *[
                        {
                            "subagent_id": slug,
                            "recommended_use": purpose,
                            "route": {"kind": "api_model", "target_id": route},
                            "effort": "medium",
                            "review_eligible": False,
                        }
                        for slug, purpose in [
                            (
                                "report-analyst",
                                "Use report_rag skill to gather PDF evidence and citations.",
                            ),
                            ("web-analyst", "Use web_research skill for dated web evidence."),
                            (
                                "forecast-analyst",
                                "Use oil_forecast and forecast for calculations.",
                            ),
                        ]
                    ],
                    {
                        "subagent_id": "oilagent-reviewer",
                        "recommended_use": "Review exact skill bytes",
                        "route": {"kind": "api_model", "target_id": route},
                        "effort": "medium",
                        "delivery": "packet",
                        "review_eligible": True,
                    },
                ],
            },
            "MCP_ENABLED": True,
            "MCP_TOOL_TIMEOUT_SEC": 60,
            "MCP_SERVERS": [
                {
                    "id": kind,
                    "name": f"OilAgent {kind}",
                    "enabled": True,
                    "schemas_at_start": kind == "analyst",
                    "allowed_tools": (
                        [
                            "answer_question",
                            "forecast",
                            "supply_cut",
                            "market_quote",
                            "search_reports",
                            "search_web_sources",
                            "submit_feedback",
                        ]
                        if kind == "analyst"
                        else []
                    ),
                    "transport": "streamable_http",
                    "url": env.get(f"{kind.upper()}_MCP_URL", f"http://127.0.0.1:{port}/mcp"),
                    "auth_header": "Authorization",
                    "auth_token": f"Bearer {env.get(token, '')}",
                }
                for kind, port, token in [
                    ("analyst", 8011, "ANALYST_MCP_TOKEN"),
                    ("evolution", 8012, "EVOLUTION_MCP_TOKEN"),
                ]
            ],
        }
    )
    for key in ["OUROBOROS_SUBAGENTS", "OUROBOROS_SKILL_SOURCES"]:
        profile[key] = json.dumps(profile[key])
    return profile


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def runtime_paths():
    root = CORE_ROOT / "workspace/ouroboros-runtime"
    python = CORE_ROOT / "workspace/ouroboros-venv/bin/python"
    return root, python


def isolated_env(root, repo):
    # Credentials come from this runtime's settings, not the parent environment.
    env = {
        key: os.environ[key]
        for key in ["PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"]
        if key in os.environ
    }
    files = configured_path("USER_FILES_PATH", "workspace/files")
    files.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            key: os.getenv(key, "")
            for key in ["OUROBOROS_LLM_BRIDGE_ENABLED", "LLM_BRIDGE_TOKEN", "LLM_MODEL"]
        }
    )
    env.update(
        {
            "PYTHONPATH": str(repo),
            "PYTHONUNBUFFERED": "1",
            "LLM_LOCK_PATH": str(configured_path("LLM_LOCK_PATH", "workspace/llm/gigachat.lock")),
            "OUROBOROS_APP_ROOT": str(root),
            "OUROBOROS_REPO_DIR": str(repo),
            "OUROBOROS_DATA_DIR": str(root / "data"),
            "OUROBOROS_SETTINGS_PATH": str(root / "data/settings.json"),
            "OUROBOROS_USER_FILES_ROOT": str(files),
            "OUROBOROS_FILE_BROWSER_DEFAULT": str(files),
            "OUROBOROS_DELIVERABLES_ROOT": str(files / "Deliverables"),
        }
    )
    return env


def prepare():
    load_dotenv(CORE_ROOT / ".env", override=False)
    root, python = runtime_paths()
    if not python.is_file():
        raise ValueError("Install upstream requirements-runtime.lock in workspace/ouroboros-venv")
    source = configured_path("OUROBOROS_PATH", "../workspace/upstream/ouroboros")
    pin = json.loads((CORE_ROOT / "config/ouroboros-pin.json").read_text())["commit"]
    repo = root / "repo"
    if not repo.exists():
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--no-hardlinks", "--no-checkout", str(source), str(repo)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "--detach", pin], check=True, capture_output=True
        )
        subprocess.run(["git", "-C", str(repo), "remote", "remove", "origin"], check=True)
    actual = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != pin:
        raise ValueError("Isolated Ouroboros checkout differs from pin")
    sys.path.insert(0, str(source))
    from ouroboros.configured_subagents import parse_configured_subagents
    from ouroboros.provider_models import ACTIVE_MODEL_SETTING_KEYS
    from ouroboros.skill_sources import parse_sources

    profile = settings_profile(
        os.environ, ACTIVE_MODEL_SETTING_KEYS, evolution_repo() / "ouroboros_skills"
    )
    parse_configured_subagents(profile["OUROBOROS_SUBAGENTS"])
    parse_sources(profile["OUROBOROS_SKILL_SOURCES"])
    private_json(root / "data/settings.json", profile)
    if not (root / "data/state/state.json").exists():
        subprocess.run(
            [
                str(python),
                "-c",
                "from pathlib import Path; from devtools.benchmarks.common.server_runner "
                "import seed_owner_state; "
                "seed_owner_state(Path(__import__('os').environ['OUROBOROS_DATA_DIR']))",
            ],
            env=isolated_env(root, repo),
            cwd=repo,
            check=True,
            timeout=30,
        )
    return root, python, repo
