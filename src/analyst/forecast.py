import json
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

from analyst.config import configured_path
from analyst.prices import history_snapshot
from analyst.rag import digest


def history_window(as_of, start_date="", end_date=""):
    end = (
        pd.Timestamp(date.fromisoformat(end_date))
        if end_date
        else as_of.to_period("M").start_time - pd.Timedelta(days=1)
    )
    last_month = min(end.to_period("M") - int(not end.is_month_end), as_of.to_period("M") - 1)
    start = (
        pd.Timestamp(date.fromisoformat(start_date))
        if start_date
        else (last_month - 119).start_time
    )
    if start > end or end > as_of:
        raise ValueError("Invalid history range; end_date must not exceed as_of")
    first_month = start.to_period("M") + int(start.day != 1)
    if not 96 <= (last_month - first_month).n + 1 <= 600:
        raise ValueError("History range requires 96..600 completed months")
    return start, end, first_month, last_month


def monthly_data(as_of, path=None, *, start_date="", end_date=""):
    start, end, first_month, last_month = history_window(as_of, start_date, end_date)
    path = path or configured_path("BRENT_DATA_PATH", "data/brent_daily.csv")
    metadata = json.loads(path.with_suffix(".json").read_text())
    if (metadata["instrument"], metadata["price_type"], metadata["unit"]) != (
        "Brent",
        "Europe spot FOB",
        "USD/bbl",
    ):
        raise ValueError("Unsupported price series")
    if digest(path.read_bytes()) != metadata["sha256"]:
        raise ValueError("Brent CSV hash mismatch")
    frame = pd.read_csv(path, parse_dates=["date"])
    if (
        frame.date.duplicated().any()
        or not frame.date.is_monotonic_increasing
        or not np.isfinite(frame.price).all()
        or (frame.price <= 0).any()
    ):
        raise ValueError("Invalid Brent observations")
    receipts = metadata.pop("receipts", [])
    if receipts:
        metadata.update(
            provenance_entries=len(receipts),
            provenance_sha256=digest(json.dumps(receipts, sort_keys=True).encode()),
        )
    periods = frame.date.dt.to_period("M")
    frame = frame[(periods >= first_month) & (periods <= last_month)]
    grouped = frame.groupby(frame.date.dt.to_period("M"))
    months = grouped.agg(price=("price", "mean"), count=("price", "count"), last=("date", "max"))
    if len(months) < 96:
        raise ValueError("At least 96 completed months are required for calibration and backtest")
    if len(months) > 600:
        raise ValueError("History range exceeds 600 months")
    if not months.index.equals(pd.period_range(months.index[0], months.index[-1], freq="M")):
        raise ValueError("Missing Brent months")
    coverage = []
    for month, row in months.iterrows():
        days = pd.bdate_range(month.start_time, month.end_time)
        ratio = row["count"] / len(days)
        if ratio < 0.75 or row["last"] < days[-1] - pd.offsets.BDay(3):
            raise ValueError("Incomplete Brent month: " + str(month))
        coverage.append(float(ratio))
    return (
        months.price,
        metadata,
        {
            "last_observation": str(months.iloc[-1]["last"].date()),
            "last_month_observations": int(months.iloc[-1]["count"]),
            "last_month_weekday_coverage": coverage[-1],
            "minimum_weekday_coverage": min(coverage),
            "requested_start_date": str(start.date()),
            "requested_end_date": str(end.date()),
            "effective_start_month": str(months.index[0]),
            "expected_end_month": str(last_month),
        },
    )


def predictions(values, horizon=6):
    log = np.log(np.asarray(values, dtype=float))
    arima = ARIMA(log, order=(1, 1, 0), trend="n").fit()
    ets = ETSModel(log, error="add", trend="add", damped_trend=True).fit(disp=False, maxiter=1000)
    if not arima.mle_retvals["converged"] or not ets.mle_retvals["converged"]:
        raise ValueError("Forecast optimization did not converge")
    distribution = arima.get_forecast(horizon)
    return {
        "ARIMA": np.asarray(distribution.predicted_mean),
        "ETS": np.asarray(ets.forecast(horizon)),
        "naive": np.repeat(log[-1], horizon),
    }, np.asarray(distribution.conf_int(alpha=0.2))


def forecast_brent(horizon_months=3, as_of="", start_date="", end_date="", *, path=None):
    if (
        isinstance(horizon_months, bool)
        or not isinstance(horizon_months, int)
        or not 1 <= horizon_months <= 6
    ):
        raise ValueError("Forecast horizon must be 1..6 months")
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    cutoff = pd.Timestamp(date.fromisoformat(as_of)) if as_of else today
    if cutoff.tzinfo is not None or pd.isna(cutoff) or cutoff > today:
        raise ValueError("as_of must be an ISO date no later than today")
    start, end, _, _ = history_window(cutoff, start_date, end_date)
    snapshot, cache = history_snapshot(str(start.date()), str(end.date()), path)
    monthly, source, coverage = monthly_data(
        cutoff, snapshot, start_date=start_date, end_date=end_date
    )
    values, n = monthly.to_numpy(), len(monthly)
    calibration = {name: [] for name in ["ARIMA", "ETS", "naive"]}
    for origin in range(n - 35, n - 23):
        forecasts, _ = predictions(values[:origin])
        actual = np.log(values[origin : origin + 6])
        for name, point in forecasts.items():
            calibration[name].append(actual - point)
    radius = {
        name: np.quantile(np.abs(errors), 0.8, axis=0) for name, errors in calibration.items()
    }
    selection = {
        name: float(np.mean(np.abs(np.expm1(errors))))
        for name, errors in calibration.items()
        if name != "naive"
    }
    selected = min(selection, key=selection.get)
    evaluation = {name: [] for name in calibration}
    for origin in range(n - 18, n - 5):
        forecasts, arima_interval = predictions(values[:origin])
        actual = values[origin : origin + 6]
        for name, point in forecasts.items():
            bounds = (
                arima_interval
                if name == "ARIMA"
                else np.column_stack([point - radius[name], point + radius[name]])
            )
            lower, upper = np.exp(bounds).T
            evaluation[name].append(
                np.column_stack(
                    [np.exp(point) - actual, (lower <= actual) & (actual <= upper), upper - lower]
                )
            )
    metrics = {}
    for name, rows in evaluation.items():
        data = np.asarray(rows)
        metrics[name] = [
            {
                "horizon": h + 1,
                "origins": len(rows),
                "mae": float(np.abs(data[:, h, 0]).mean()),
                "rmse": float(np.sqrt(np.square(data[:, h, 0]).mean())),
                "coverage": float(data[:, h, 1].mean()),
                "mean_interval_width": float(data[:, h, 2].mean()),
            }
            for h in range(6)
        ]
    forecasts, arima_interval = predictions(values, horizon_months)
    result = {}
    for name, point in forecasts.items():
        bounds = (
            arima_interval
            if name == "ARIMA"
            else np.column_stack(
                [point - radius[name][:horizon_months], point + radius[name][:horizon_months]]
            )
        )
        result[name] = {
            "interval_method": "model_based_log_gaussian"
            if name == "ARIMA"
            else "absolute_log_error_quantile_by_horizon",
            "calibration_origins": 0 if name == "ARIMA" else 12,
            "points": [
                {
                    "month": str(monthly.index[-1] + h + 1),
                    "value": float(np.exp(point[h])),
                    "lower": float(np.exp(bounds[h, 0])),
                    "upper": float(np.exp(bounds[h, 1])),
                }
                for h in range(horizon_months)
            ],
        }
        if not np.isfinite(np.exp(np.r_[point, bounds.ravel()])).all():
            raise ValueError("Non-finite forecast")
    warnings = [
        "Интервалы не охватывают все структурные и геополитические шоки.",
        "Кеш может содержать загрузки разных дат; "
        "исторические версии публикаций не восстанавливаются.",
    ]
    if str(monthly.index[-1]) != coverage["expected_end_month"]:
        warnings.append("stale_data: прогноз начинается после data_end, а не текущего месяца.")
    if end_date and monthly.index[-1] < cutoff.to_period("M") - 1:
        warnings.append("Прогноз построен от конца заданного исторического диапазона.")
    if not cache["complete"]:
        warnings.append(
            "Не весь запрошенный диапазон опубликован или загружен; пробелы указаны в data_cache."
        )
    if coverage["last_month_weekday_coverage"] < 1:
        warnings.append(
            "Средние рассчитаны по доступным наблюдениям; есть праздники и лаг публикации."
        )
    if sum(m["mae"] for m in metrics["naive"]) < sum(m["mae"] for m in metrics[selected]):
        warnings.append(
            "Naive лучше выбранной модели по средней MAE для h=1..6 на отложенном периоде."
        )
    return {
        "instrument": "Brent",
        "price_type": "Europe spot FOB",
        "unit": "USD/bbl",
        "frequency": "monthly",
        "point_estimate": "conditional median of monthly average",
        "as_of": str(cutoff.date()),
        "data_end": str(monthly.index[-1]),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_months": horizon_months,
        "interval_level": 0.8,
        "selected_model": selected,
        "model_spec": {
            "ARIMA": "(1,1,0), no drift, log(price)",
            "ETS": "additive error and damped additive trend, no seasonality, log(price)",
        },
        "forecasts": result,
        "backtest_by_horizon": metrics,
        "selection_relative_error": selection,
        "backtest_protocol": {
            "calibration_origins": 12,
            "test_origins": 13,
            "calibration_last_target": str(monthly.index[n - 19]),
            "first_test_training_end": str(monthly.index[n - 19]),
        },
        "data_source": source,
        "data_cache": cache,
        "data_coverage": coverage,
        "warnings": warnings,
    }


def render_forecast(result):
    name = result["selected_model"]
    paragraphs = [
        f"Расчётный прогноз Brent spot, USD/bbl; {name}. Данные по {result['data_end']}. "
        "Точки — условные медианы среднемесячной цены; прогнозный интервал 80%.",
    ]
    for model in ["ARIMA", "ETS"]:
        table = ["| Месяц | Оценка, USD/bbl | Нижняя 80% | Верхняя 80% |", "|---|---:|---:|---:|"]
        table += [
            f"| {p['month']} | {p['value']:.2f} | {p['lower']:.2f} | {p['upper']:.2f} |"
            for p in result["forecasts"][model]["points"]
        ]
        paragraphs.append(f"{model} [F1]\n\n" + "\n".join(table))
    paragraphs += [
        "ARIMA и ETS рассчитаны отдельно; выбор сделан на calibration, не на test.",
        "Ограничения: " + " ".join(result["warnings"]),
        "[F1] Исторический дневной ряд: "
        + result["data_source"].get("title", "Brent spot")
        + ", USD/bbl; "
        "средние по доступным наблюдениям месяца. Последнее дневное наблюдение: "
        + result["data_coverage"]["last_observation"]
        + ". "
        + result["data_source"]["source_url"],
    ]
    return "\n\n".join(paragraphs)
