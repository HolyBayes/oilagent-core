import json
import os
import time
from pathlib import Path

from analyst.config import configured_path


def save_trace(result):
    directory = configured_path("TRACE_PATH", "workspace/traces")
    directory.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - int(os.getenv("TRACE_RETENTION_DAYS", "7")) * 86400
    for path in directory.glob("*.json"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
    path = directory / f"{result['request_id']}.json"
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
        content = json.dumps(result, ensure_ascii=False, indent=2)
        for name, value in os.environ.items():
            if (
                value
                and len(value) >= 12
                and any(k in name for k in ("TOKEN", "CREDENTIALS", "API_KEY"))
            ):
                content = content.replace(value, "[redacted]")
        handle.write(content)
    temporary.replace(path)
    return str(Path(path).name)


def record_feedback(request_id, rating, comment):
    from datetime import datetime, timezone
    from uuid import UUID

    request_id = str(UUID(request_id))
    if rating not in {-1, 0, 1} or not 1 <= len(comment) <= 2000:
        raise ValueError("Feedback requires rating -1/0/1 and comment 1..2000 characters")
    directory = configured_path("TRACE_PATH", "workspace/traces")
    if not (directory / f"{request_id}.json").is_file():
        raise ValueError("Unknown request trace")
    data = {
        "request_id": request_id,
        "rating": rating,
        "comment": comment,
        "kind": "unverified_user_feedback",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path = directory / f"{request_id}.feedback.json"
    with open(path, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as handle:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        for name, value in os.environ.items():
            if (
                value
                and len(value) >= 12
                and any(k in name for k in ("TOKEN", "CREDENTIALS", "API_KEY"))
            ):
                content = content.replace(value, "[redacted]")
        handle.write(content)
    return {"request_id": request_id, "stored": True, "automatically_used_as_truth": False}
