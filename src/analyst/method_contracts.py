"""Protected output validation; evolved code cannot supply provenance or test targets."""

import math

import numpy as np


def validate(slot, request, result):
    if slot == "forecast":
        horizon = request["horizon"]
        if any(
            not isinstance(result["spec"].get(name), str)
            or not 1 <= len(result["spec"][name]) <= 300
            for name in ["ARIMA", "ETS"]
        ):
            raise ValueError("Forecast model specification is required")
        points = {
            name: np.asarray(result["points"][name], dtype=float) for name in ["ARIMA", "ETS"]
        }
        bounds = np.asarray(result["arima_interval"], dtype=float)
        if (
            any(p.shape != (horizon,) for p in points.values())
            or bounds.shape != (horizon, 2)
            or not np.isfinite(np.concatenate([*points.values(), bounds.ravel()])).all()
            or not (bounds[:, 0] <= points["ARIMA"]).all()
            or not (points["ARIMA"] <= bounds[:, 1]).all()
        ):
            raise ValueError("Invalid forecast result contract")
        points["naive"] = np.repeat(np.log(request["values"][-1]), horizon)
        return points, bounds
    if slot in {"reranking", "search_strategy"}:
        if (
            not isinstance(result, list)
            or any(type(i) is not int for i in result)
            or sorted(result) != list(range(len(request["rows"])))
        ):
            raise ValueError("Ranking must return a permutation of input indices")
        return result
    if slot == "chunking":
        previous, covered, total = -1, 0, 0
        if not isinstance(result, list) or len(result) > 200:
            raise ValueError("Invalid chunk count")
        for span in result:
            if (
                not isinstance(span, list)
                or len(span) != 2
                or any(type(i) is not int for i in span)
            ):
                raise ValueError("Chunk spans must contain two integer offsets")
            a, b = span
            if not (previous < a < b <= len(request["text"])) or b - a > 8000:
                raise ValueError("Invalid source span")
            if request["text"][covered:a].strip():
                raise ValueError("Chunking omitted source text")
            previous, covered, total = a, max(covered, b), total + b - a
        if request["text"][covered:].strip() or total > 3 * max(1, len(request["text"])):
            raise ValueError("Incomplete or excessive chunk coverage")
        return result
    if slot == "scenario":
        if (
            not isinstance(result, list)
            or len(result) != 4
            or any(type(x) not in {int, float} or not math.isfinite(x) or x <= 0 for x in result)
        ):
            raise ValueError("Invalid scenario prices")
        return result
    raise ValueError("Unknown method contract")
