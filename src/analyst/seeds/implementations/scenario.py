import math
from itertools import product


def run(request):
    return [
        request["initial_price"]
        * math.exp(math.log1p(-request["cut_mbd"] / request["supply_mbd"]) / (d - s))
        for d, s in product(request["demand_elasticity"], request["supply_elasticity"])
    ]
