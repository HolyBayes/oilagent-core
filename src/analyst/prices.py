import fcntl
import io
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from analyst.config import CORE_ROOT, configured_path
from analyst.rag import digest

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def merge_ranges(ranges):
    merged = []
    for lo, hi in sorted((date.fromisoformat(a), date.fromisoformat(b)) for a, b in ranges):
        if lo > hi:
            raise ValueError("Invalid cached coverage")
        if merged and lo <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [[a.isoformat(), b.isoformat()] for a, b in merged]


def missing_ranges(start, end, covered):
    cursor, last = date.fromisoformat(start), date.fromisoformat(end)
    if cursor > last:
        raise ValueError("Invalid history range")
    missing = []
    for a, b in merge_ranges(covered):
        lo, hi = date.fromisoformat(a), date.fromisoformat(b)
        if cursor < lo:
            missing.append([cursor.isoformat(), min(last, lo - timedelta(days=1)).isoformat()])
        cursor = max(cursor, hi + timedelta(days=1))
        if cursor > last:
            break
    if cursor <= last:
        missing.append([cursor.isoformat(), last.isoformat()])
    return missing


def download_history(start, end):
    response = httpx.get(
        FRED_URL,
        params={"id": "DCOILBRENTEU", "cosd": start, "coed": end},
        timeout=25,
        follow_redirects=True,
    )
    response.raise_for_status()
    frame = pd.read_csv(io.BytesIO(response.content), na_values=["."])
    if len(frame.columns) != 2:
        raise ValueError("Unexpected FRED CSV")
    frame.columns = ["date", "price"]
    frame["date"] = pd.to_datetime(frame.date)
    frame["price"] = pd.to_numeric(frame.price)
    frame = frame.dropna(subset=["price"])
    frame = frame[(frame.date >= start) & (frame.date <= end)]
    if (
        frame.date.isna().any()
        or frame.date.duplicated().any()
        or not np.isfinite(frame.price).all()
        or (frame.price <= 0).any()
    ):
        raise ValueError("Invalid EIA/FRED observations")
    return frame.sort_values("date"), {
        "url": str(response.url),
        "requested": [start, end],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "raw_sha256": digest(response.content),
    }


def store_snapshot(directory, frame, metadata):
    data = frame.to_csv(index=False, date_format="%Y-%m-%d").encode()
    metadata = {**metadata, "sha256": digest(data)}
    key = digest(json.dumps(metadata, sort_keys=True).encode() + data)
    csv = directory / f"{key}.csv"
    csv.write_bytes(data)
    csv.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    temp = directory / "index.tmp"
    temp.write_text(json.dumps({"snapshot": key}))
    temp.replace(directory / "index.json")
    return csv


def history_snapshot(start, end, path=None):
    directory = configured_path("BRENT_CACHE_PATH", "workspace/prices")
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("Invalid history range")
    local = (
        Path(path)
        if path is not None
        else (configured_path("BRENT_DATA_PATH", "") if os.getenv("BRENT_DATA_PATH") else None)
    )
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "history.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pointer = directory / "index.json"
        current = local or CORE_ROOT / "data/brent_daily.csv"
        if local is None and pointer.exists():
            key = json.loads(pointer.read_text())["snapshot"]
            if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                raise ValueError("Invalid history cache pointer")
            current = directory / f"{key}.csv"
        metadata = json.loads(current.with_suffix(".json").read_text())
        if digest(current.read_bytes()) != metadata["sha256"]:
            raise ValueError("History cache hash mismatch")
        if local is None and pointer.exists():
            expected = digest(json.dumps(metadata, sort_keys=True).encode() + current.read_bytes())
            if expected != key:
                raise ValueError("History cache manifest hash mismatch")
        frame = pd.read_csv(current, parse_dates=["date"])
        covered = metadata.get("coverage") or [
            [str(frame.date.min().date()), str(frame.date.max().date())]
        ]
        missing = missing_ranges(start, end, covered)
        if local is not None:
            return current, {
                "state": "local_csv",
                "network_used": False,
                "complete": not missing,
                "requested": [start, end],
                "missing": missing,
            }
        metadata = {
            **metadata,
            "coverage": covered,
            "receipts": metadata.get(
                "receipts",
                [
                    {
                        "url": metadata["source_url"],
                        "retrieved_at": metadata["retrieved_at"],
                        "coverage": covered,
                        "raw_sha256": metadata.get("raw_sha256"),
                    }
                ],
            ),
        }
        changed, errors = not pointer.exists(), []
        for lo, hi in missing:
            try:
                extra, receipt = download_history(lo, hi)
                extra = extra[(extra.date >= lo) & (extra.date <= hi)]
                combined = (
                    pd.concat([frame, extra])
                    .drop_duplicates("date", keep="first")
                    .sort_values("date")
                )
                watermark = combined.date.max().date()
                stop = min(date.fromisoformat(hi), watermark)
                while stop < date.fromisoformat(hi) and (stop + timedelta(days=1)).weekday() >= 5:
                    stop += timedelta(days=1)
                if date.fromisoformat(lo) <= stop:
                    covered = merge_ranges([*covered, [lo, stop.isoformat()]])
                    frame, changed = combined, True
                    metadata["receipts"].append(receipt)
                    metadata["retrieved_at"] = receipt["retrieved_at"]
                    metadata["source_url"] = "https://fred.stlouisfed.org/series/DCOILBRENTEU"
                    metadata.pop("raw_sha256", None)
            except Exception as exc:
                errors.append({"range": [lo, hi], "error_type": type(exc).__name__})
        metadata["coverage"] = covered
        csv = store_snapshot(directory, frame, metadata) if changed else current
        remaining = missing_ranges(start, end, covered)
        return csv, {
            "state": "partial" if remaining else ("extended" if missing else "hit"),
            "network_used": bool(missing),
            "requested": [start, end],
            "missing": remaining,
            "requested_from_provider": missing,
            "errors": errors,
            "snapshot": csv.stem,
            "complete": not remaining,
        }
