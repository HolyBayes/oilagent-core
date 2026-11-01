import json
from datetime import datetime, timezone

import httpx
import pandas as pd
import pytest

from analyst import prices
from analyst.config import CORE_ROOT
from analyst.forecast import monthly_data


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BRENT_CACHE_PATH", str(tmp_path))
    monkeypatch.setenv("BRENT_DATA_PATH", "")
    frame = pd.read_csv(CORE_ROOT / "data/brent_daily.csv", parse_dates=["date"])
    metadata = json.loads((CORE_ROOT / "data/brent_daily.json").read_text())
    metadata["coverage"] = [["2016-01-11", "2016-01-20"], ["2016-01-25", "2016-02-10"]]
    selected = frame[
        ((frame.date >= "2016-01-11") & (frame.date <= "2016-01-20"))
        | ((frame.date >= "2016-01-25") & (frame.date <= "2016-02-10"))
    ]
    prices.store_snapshot(tmp_path, selected, metadata)
    calls = []

    def download(start, end):
        calls.append([start, end])
        return frame[(frame.date >= start) & (frame.date <= end)], {
            "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
            "requested": [start, end],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(prices, "download_history", download)
    return tmp_path, calls


def test_download_only_missing_intervals_then_reuse_subrange(cache):
    _, calls = cache
    path, info = prices.history_snapshot("2016-01-01", "2016-02-20")
    assert calls == [
        ["2016-01-01", "2016-01-10"],
        ["2016-01-21", "2016-01-24"],
        ["2016-02-11", "2016-02-20"],
    ]
    assert info["complete"] and info["state"] == "extended"
    frame = pd.read_csv(path)
    assert frame.date.is_unique and frame.date.is_monotonic_increasing
    second, hit = prices.history_snapshot("2016-01-05", "2016-02-15")
    assert second == path and hit["state"] == "hit" and not hit["network_used"]
    assert len(calls) == 3


def test_expand_both_edges_without_overwriting_cached_values(cache):
    _, calls = cache
    path, _ = prices.history_snapshot("2016-01-01", "2016-02-20")
    before = pd.read_csv(path).set_index("date")
    calls.clear()
    path, info = prices.history_snapshot("2015-12-20", "2016-03-10")
    assert calls == [["2015-12-20", "2015-12-31"], ["2016-02-21", "2016-03-10"]]
    after = pd.read_csv(path).set_index("date")
    pd.testing.assert_frame_equal(before, after.loc[before.index])
    assert info["complete"]


def test_failed_fetch_keeps_cache_and_reports_missing_range(cache, monkeypatch):
    def unavailable(*args):
        raise httpx.ReadTimeout("private transport detail")

    monkeypatch.setattr(prices, "download_history", unavailable)
    path, result = prices.history_snapshot("2016-01-01", "2016-02-20")
    assert not result["complete"] and result["state"] == "partial"
    assert len(result["missing"]) == 3 and len(result["errors"]) == 3
    assert "private transport" not in json.dumps(result)
    assert len(pd.read_csv(path)) > 0


def test_cache_corruption_is_rejected(cache):
    directory, calls = cache
    key = json.loads((directory / "index.json").read_text())["snapshot"]
    path = directory / f"{key}.csv"
    path.write_text(path.read_text() + "tampered")
    with pytest.raises(ValueError, match="hash"):
        prices.history_snapshot("2016-01-12", "2016-01-15")
    assert not calls


def test_range_controls_training_window_instead_of_silent_120_month_cap():
    path = CORE_ROOT / "data/brent_daily.csv"
    y, _, coverage = monthly_data(
        pd.Timestamp("2025-10-01"), path, start_date="2010-01-01", end_date="2025-09-30"
    )
    assert str(y.index[0]) == "2010-01" and str(y.index[-1]) == "2025-09"
    assert len(y) == 189 and coverage["requested_end_date"] == "2025-09-30"


def test_incomplete_first_and_last_months_of_requested_range_are_excluded():
    path = CORE_ROOT / "data/brent_daily.csv"
    y, _, _ = monthly_data(
        pd.Timestamp("2025-10-01"), path, start_date="2010-01-15", end_date="2025-09-15"
    )
    assert str(y.index[0]) == "2010-02" and str(y.index[-1]) == "2025-08"


def test_unpublished_tail_is_not_permanently_cached_as_empty(cache, monkeypatch):
    frame = pd.DataFrame({"date": pd.to_datetime([]), "price": []})
    monkeypatch.setattr(
        prices, "download_history", lambda a, b: (frame, {"retrieved_at": "2026-11-01"})
    )
    _, result = prices.history_snapshot("2016-02-11", "2016-02-19")
    assert result["missing"] == [["2016-02-11", "2016-02-19"]]
    assert not result["complete"]
