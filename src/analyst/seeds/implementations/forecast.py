import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.exponential_smoothing.ets import ETSModel


def run(request):
    values, horizon = request["values"], request["horizon"]
    log = np.log(np.asarray(values, dtype=float))
    arima = ARIMA(log, order=(1, 1, 0), trend="n").fit()
    ets = ETSModel(log, error="add", trend="add", damped_trend=True).fit(disp=False, maxiter=1000)
    if not arima.mle_retvals["converged"] or not ets.mle_retvals["converged"]:
        raise ValueError("Forecast optimization did not converge")
    distribution = arima.get_forecast(horizon)
    points = {
        "ARIMA": np.asarray(distribution.predicted_mean),
        "ETS": np.asarray(ets.forecast(horizon)),
    }
    return {
        "spec": {
            "ARIMA": "(1,1,0), no drift, log(price)",
            "ETS": "additive error and damped additive trend, no seasonality, log(price)",
        },
        "points": {k: v.tolist() for k, v in points.items()},
        "arima_interval": np.asarray(distribution.conf_int(alpha=0.2)).tolist(),
    }
