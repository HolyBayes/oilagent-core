import numpy as np
import pytest

from analyst.method_contracts import validate


def test_forecast_naive_benchmark_is_owned_by_core():
    points, _ = validate(
        "forecast",
        {"horizon": 1, "values": [70.0]},
        {
            "spec": {"ARIMA": "fixture", "ETS": "fixture"},
            "points": {"ARIMA": [4.0], "ETS": [4.1], "naive": [999.0]},
            "arima_interval": [[3.9, 4.2]],
        },
    )
    assert points["naive"][0] == np.log(70.0)


@pytest.mark.parametrize("result", [[0, 0], [0, 2], [True, 1], [{"text": "forged"}, 1]])
def test_ranking_cannot_replace_passages_or_omit_indices(result):
    with pytest.raises(ValueError, match="permutation"):
        validate("reranking", {"rows": [{"text": "original"}, {"text": "another"}]}, result)


@pytest.mark.parametrize("spans", [[[0, 3]], [[4, 11]], [[0, 12]], [[0, 5], [0, 11]]])
def test_chunking_cannot_drop_or_forge_source_text(spans):
    with pytest.raises(ValueError):
        validate("chunking", {"text": "Oil supply."}, spans)
