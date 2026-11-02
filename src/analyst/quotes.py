"""Public delayed exchange quotes; these are futures, not EIA spot prices."""

import math
import os
from datetime import datetime, timezone

import httpx

SYMBOLS = {"Brent": "BZ=F", "WTI": "CL=F"}


def latest_quote(instrument="Brent"):
    instrument = next(
        (name for name in SYMBOLS if name.casefold() == instrument.casefold()), instrument
    )
    if instrument not in SYMBOLS:
        raise ValueError("Only Brent and WTI futures quotes are available")
    symbol = SYMBOLS[instrument]
    response = httpx.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"interval": "1d", "range": "5d"},
        headers={"User-Agent": "OilAgent/0.1 public-data-demo"},
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    meta = result["meta"]
    value, timestamp = float(meta["regularMarketPrice"]), int(meta["regularMarketTime"])
    now = datetime.now(timezone.utc)
    observed = datetime.fromtimestamp(timestamp, timezone.utc)
    age = (now - observed).total_seconds()
    if (
        meta.get("symbol") != symbol
        or meta.get("currency") != "USD"
        or not math.isfinite(value)
        or value <= 0
        or age < 0
    ):
        raise ValueError("Invalid quote provenance")
    stale = age > float(os.getenv("QUOTE_MAX_AGE_SEC", "345600"))
    return {
        "instrument": instrument,
        "symbol": symbol,
        "price_type": "exchange futures",
        "value": value,
        "unit": "USD/bbl",
        "timestamp": observed.isoformat(),
        "retrieved_at": now.isoformat(),
        "exchange": meta.get("exchangeName", ""),
        "contract": meta.get("shortName", ""),
        "delayed": True,
        "stale": stale,
        "source_url": f"https://finance.yahoo.com/quote/{symbol}/",
        "limitations": [
            "Котировка фьючерса с задержкой; не текущая EIA spot цена.",
            "Показано время последней сделки; рынок может быть закрыт.",
        ],
    }


def render_quote(quote):
    return (
        f"Последняя доступная котировка {quote['instrument']} ({quote['symbol']}, фьючерс): "
        f"{quote['value']:.2f} {quote['unit']}. Время сделки {quote['timestamp']}. "
        + " ".join(quote["limitations"])
        + f" Источник: {quote['source_url']}"
    )
