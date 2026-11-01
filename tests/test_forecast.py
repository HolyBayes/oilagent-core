import json

import numpy as np
import pandas as pd
import pytest

from analyst import graph as pipeline
from analyst.config import CORE_ROOT
from analyst.contracts import Route
from analyst.forecast import forecast_brent, monthly_data, render_forecast
from analyst.rag import digest

SNAPSHOT = CORE_ROOT / "data/brent_daily.csv"


def snapshot(tmp_path, frame):
    path = tmp_path / "brent.csv"
    frame.to_csv(path, index=False)
    metadata = json.loads(SNAPSHOT.with_suffix(".json").read_text())
    metadata["sha256"] = digest(path.read_bytes())
    path.with_suffix(".json").write_text(json.dumps(metadata))
    return path


def test_both_models_intervals_and_separate_backtest():
    result = forecast_brent(3, "2025-10-01", path=SNAPSHOT)
    assert result["data_end"] == "2025-09"
    assert result["selected_model"] in {"ARIMA", "ETS"}
    answer = render_forecast(result)
    assert "ARIMA [F1]" in answer and "ETS [F1]" in answer
    assert "Исторический дневной ряд" in answer and "USD/bbl" in answer and "80%" in answer
    assert result["data_source"]["source_url"] in answer
    assert set(result["forecasts"]) == {"ARIMA", "ETS", "naive"}
    protocol = result["backtest_protocol"]
    assert protocol["calibration_last_target"] <= protocol["first_test_training_end"]
    for model in result["forecasts"].values():
        assert [p["month"] for p in model["points"]] == ["2025-10", "2025-11", "2025-12"]
        assert all(0 < p["lower"] <= p["value"] <= p["upper"] for p in model["points"])
        assert all(np.isfinite(list(p.values())[1:]).all() for p in model["points"])
    for metrics in result["backtest_by_horizon"].values():
        assert [m["horizon"] for m in metrics] == list(range(1, 7))
        assert all(m["origins"] == 13 and 0 <= m["coverage"] <= 1 for m in metrics)


def test_future_observations_cannot_change_historical_training(tmp_path):
    cutoff = pd.Timestamp("2025-10-16")
    before, _, _ = monthly_data(cutoff, SNAPSHOT)
    frame = pd.read_csv(SNAPSHOT)
    frame.loc[frame.date >= "2025-10-01", "price"] = 99999
    after, _, _ = monthly_data(cutoff, snapshot(tmp_path, frame))
    pd.testing.assert_series_equal(before, after)
    assert str(after.index[-1]) == "2025-09"


@pytest.mark.parametrize("problem", ["duplicate", "negative", "missing_month", "short"])
def test_invalid_data_is_rejected(tmp_path, problem):
    frame = pd.read_csv(SNAPSHOT)
    if problem == "duplicate":
        frame = pd.concat([frame, frame.tail(1)])
    elif problem == "negative":
        frame.loc[frame.index[-1], "price"] = -1
    elif problem == "missing_month":
        frame = frame[~frame.date.str.startswith("2025-06")]
    else:
        frame = frame.tail(20)
    with pytest.raises(ValueError):
        monthly_data(pd.Timestamp("2026-11-01"), snapshot(tmp_path, frame))


def test_hash_and_horizon_validation(tmp_path):
    path = snapshot(tmp_path, pd.read_csv(SNAPSHOT))
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash"):
        monthly_data(pd.Timestamp("2025-10-01"), path)
    for horizon in [0, 7, True, 1.5]:
        with pytest.raises(ValueError, match="horizon"):
            forecast_brent(horizon, path=SNAPSHOT)


def test_graph_selects_calculation_without_web_or_synthesis(monkeypatch):
    monkeypatch.setenv("BRENT_DATA_PATH", str(SNAPSHOT))
    monkeypatch.setattr(pipeline, "model_ready", lambda: True)

    def route_only(schema, messages):
        assert schema is Route
        return Route(
            intent="forecast",
            freshness_required=False,
            horizon_months=2,
            as_of="2025-10-01",
            start_date="2010-01-01",
            end_date="2025-09-30",
        ), {"total_tokens": 10}

    monkeypatch.setattr(pipeline, "invoke_structured", route_only)
    monkeypatch.setattr(pipeline, "search_web", lambda *a, **k: pytest.fail("Unexpected web"))
    result = pipeline.answer_question("Рассчитай новый прогноз Brent на два месяца")
    assert result["status"] == "forecasted"
    assert len(result["forecast"]["forecasts"]["ARIMA"]["points"]) == 2
    assert result["forecast"]["data_coverage"]["effective_start_month"] == "2010-01"
    assert result["forecast"]["data_cache"]["requested"] == ["2010-01-01", "2025-09-30"]
    assert result["usage"] == {"route": {"total_tokens": 10}}
