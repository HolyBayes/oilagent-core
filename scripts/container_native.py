"""Prepare isolated container settings; normal native review/enable remains required."""

import json
import os
import runpy
from pathlib import Path

from ouroboros.provider_models import ACTIVE_MODEL_SETTING_KEYS

from analyst.runtime import private_json, settings_profile

root = Path(os.environ["OUROBOROS_APP_ROOT"])
settings = root / "data/settings.json"
profile = settings_profile(
    os.environ, ACTIVE_MODEL_SETTING_KEYS, Path("/evolution/ouroboros_skills")
)
existing = json.loads(settings.read_text()) if settings.exists() else {}
for key in ("GIGACHAT_CREDENTIALS", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
    existing.pop(key, None)
private_json(settings, {**existing, **profile})
state = root / "data/state/state.json"
if not state.exists():
    from devtools.benchmarks.common.server_runner import seed_owner_state

    seed_owner_state(root / "data")
# Do not grant/install/review skills without the native hash-bound lifecycle.
runpy.run_path("/opt/core/scripts/native_ouroboros.py", run_name="__main__")
