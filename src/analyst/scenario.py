import math
from itertools import product
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupplyScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    initial_price: float = Field(gt=0)
    supply_mbd: float = Field(gt=0)
    cut_mbd: float = Field(gt=0)
    demand_elasticity: tuple[float, float]
    supply_elasticity: tuple[float, float]
    assumptions: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def valid_ranges(self):
        if not self.cut_mbd < self.supply_mbd:
            raise ValueError("cut_mbd must be less than supply_mbd")
        d, s = self.demand_elasticity, self.supply_elasticity
        if not d[0] <= d[1] < 0 or not 0 <= s[0] <= s[1]:
            raise ValueError("Require demand low <= high < 0 and supply 0 <= low <= high")
        return self


def supply_cut_scenario(inputs: dict) -> dict:
    params = SupplyScenario.model_validate(inputs)
    values = [
        params.initial_price * math.exp(math.log1p(-params.cut_mbd / params.supply_mbd) / (d - s))
        for d, s in product(params.demand_elasticity, params.supply_elasticity)
    ]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Scenario is numerically unstable")
    return {
        "run_id": str(uuid4()),
        "inputs": params.model_dump(),
        "formula": "P1 = P0 * (1 - cut_mbd / supply_mbd) ** (1 / (eps_d - eps_s))",
        "unit": "USD/bbl",
        "price_range": [min(values), max(values)],
        "kind": "conditional_sensitivity",
        "limitations": [
            "Условная статическая оценка при пользовательских допущениях, не прогноз ARIMA/ETS.",
            "Постоянные эластичности; прочие условия неизменны; "
            "компенсация сокращения отсутствует.",
            "Диапазон чувствительности не является статистическим доверительным интервалом.",
        ],
    }


def render_scenario(result):
    lo, hi = result["price_range"]
    return (
        f"При заданных допущениях диапазон цены: {lo:.2f}–{hi:.2f} USD/bbl.\n\n"
        f"Формула: `{result['formula']}`.\n\n"
        f"Допущения: {result['inputs']['assumptions']}\n\n" + " ".join(result["limitations"])
    )
