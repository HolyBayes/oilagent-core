"""Five explicit live Lite scenarios through authenticated Analyst MCP; no native UI claim."""

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
questions = [
    (
        "report",
        "Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026?",
    ),
    ("web", "Какие свежие новости о природном газе опубликовало EIA за последние 7 дней?"),
    (
        "hybrid",
        "Что EIA в отчёте за октябрь 2025 прогнозировало для цены Brent в первом полугодии 2026; "
        "а затем добавь последние новости EIA о природном газе за 7 дней. Раздели источники.",
    ),
    (
        "forecast",
        "Рассчитай новый прогноз Brent на 3 месяца с интервалами 80%, as_of 2026-10-01, "
        "история 2016-10-01 — 2026-09-30.",
    ),
    ("out_of_scope", "Напиши рецепт борща."),
]
results = []
path = Path("docs/lite-delivery-evidence.json")
with httpx.Client(timeout=140, trust_env=False) as c:
    for case, question in questions:
        r = c.post(
            "http://127.0.0.1:" + os.getenv("ANALYST_PORT", "8011") + "/mcp",
            headers={
                "Authorization": "Bearer " + os.environ["ANALYST_MCP_TOKEN"],
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "answer_question", "arguments": {"question": question}},
            },
        )
        r.raise_for_status()
        body = r.json()["result"]
        result = json.loads(body["content"][0]["text"]) if not body.get("isError") else body
        results.append({"case": case, "question": question, "result": result})
        path.write_text(
            json.dumps(
                {
                    "transport": "HTTP Analyst MCP; not native Main",
                    "model": os.getenv("GIGACHAT_MODEL"),
                    "cases": results,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(case, result.get("status"), flush=True)
