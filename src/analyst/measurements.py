"""Conservative normalization; unknown definitions must still match exactly."""

import re
from decimal import Decimal


def label(value):
    return re.sub(r"[\s_]+", " ", value.strip().casefold())


def unit(value):
    key = re.sub(r"\s+", "", value.casefold())
    aliases = {
        "mb/d": ("mb/d", "1"),
        "millionb/d": ("mb/d", "1"),
        "millionbarrelsperday": ("mb/d", "1"),
        "млнб/с": ("mb/d", "1"),
        "tb/d": ("mb/d", ".001"),
        "kb/d": ("mb/d", ".001"),
        "thousandbarrelsperday": ("mb/d", ".001"),
        "тысб/с": ("mb/d", ".001"),
        "b/d": ("mb/d", ".000001"),
        "barrelsperday": ("mb/d", ".000001"),
        "usd/bbl": ("USD/bbl", "1"),
        "$/b": ("USD/bbl", "1"),
        "usd/barrel": ("USD/bbl", "1"),
        "dollarsperbarrel": ("USD/bbl", "1"),
        "%": ("percent", "1"),
        "percent": ("percent", "1"),
    }
    name, factor = aliases.get(key, (key, "1"))
    return name, Decimal(factor)


def period(value):
    key = re.sub(r"\s+", "", value.upper())
    match = re.fullmatch(r"([HQ])([1-4])(\d{4})", key)
    if match:
        return match[3] + "-" + match[1] + match[2]
    match = re.fullmatch(r"([1-4])([HQ])(\d{4})", key)
    if match:
        return match[3] + "-" + match[2] + match[1]
    match = re.fullmatch(r"(\d{4})-?([HQ][1-4])", key)
    if match:
        return match[1] + "-" + match[2]
    match = re.fullmatch(r"(\d{4})-01-01/\1-(06-30|12-31)", key)
    if match:
        return match[1] + ("-H1" if match[2] == "06-30" else "")
    return key


def comparable(claim):
    name, factor = unit(claim["unit"])
    geography = label(claim["geography"])
    geography = {
        "world": "global",
        "мир": "global",
        "мировой": "global",
        "united states": "usa",
        "us": "usa",
        "сша": "usa",
    }.get(geography, geography)
    metric = label(claim["metric"])
    metric = {
        "oil demand growth": "oil demand growth",
        "рост спроса на нефть": "oil demand growth",
    }.get(metric, metric)
    vintage = claim["vintage"].strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", vintage):
        vintage = vintage[:7]
    return {
        "metric": metric,
        "geography": geography,
        "unit": name,
        "period": period(claim["period"]),
        "vintage": vintage,
        "observation_type": claim["observation_type"],
        "value": Decimal(claim["value"].replace(",", ".")) * factor,
    }
