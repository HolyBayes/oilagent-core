"""Prepare isolated container settings; normal native review/enable remains required."""

import os
import runpy
from pathlib import Path

from ouroboros.provider_models import ACTIVE_MODEL_SETTING_KEYS

from analyst.runtime import private_json, settings_profile

root = Path(os.environ["OUROBOROS_APP_ROOT"])
settings = root / "data/settings.json"
if not settings.exists():
    profile = settings_profile(
        os.environ, ACTIVE_MODEL_SETTING_KEYS, Path("/evolution/ouroboros_skills")
    )
    private_json(settings, profile)
state = root / "data/state/state.json"
if not state.exists():
    from devtools.benchmarks.common.server_runner import seed_owner_state

    seed_owner_state(root / "data")
# Do not grant/install/review skills without the native hash-bound lifecycle.
runpy.run_path("/opt/core/scripts/native_ouroboros.py", run_name="__main__")
