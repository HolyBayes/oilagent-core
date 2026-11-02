"""Small deterministic BM25 reranker over a frozen report collection."""

import math
import re
from collections import Counter

ALIASES = {
    "спрос": "demand",
    "миров": "global",
    "world": "global",
    "прогноз": "forecast",
    "производ": "production",
    "перв": "first",
    "полугод": "half",
    "уров": "average",
    "добыч": "production",
    "запас": "inventories",
    "корзин": "basket",
    "кита": "china",
    "прирост": "growth",
    "рост": "growth",
    "цен": "price",
    "сентябр": "september",
    "средн": "average",
    "предложен": "supply",
}


def tokens(text):
    words = re.findall(r"[a-zа-яё0-9]+", text.lower())
    return [
        next((v for k, v in ALIASES.items() if w.startswith(k)), w)
        for w in words
        if len(w) > 2
        and w not in {"the", "and", "for", "what", "does", "which", "report", "outlook"}
    ]


def rerank(rows, query, weight=1.0):
    if not rows:
        return rows
    docs = [Counter(tokens(row["text"])) for row in rows]
    lengths = [sum(d.values()) for d in docs]
    average = sum(lengths) / len(docs) or 1
    wanted = set(tokens(query))
    frequency = {t: sum(t in d for d in docs) for t in wanted}

    def score(i):
        total = 0
        for term in wanted:
            tf = docs[i][term]
            idf = math.log(1 + (len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            total += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[i] / average))
        return total

    lexical = sorted(range(len(rows)), key=lambda i: (-score(i), i))
    ranks = {i: r for r, i in enumerate(lexical)}
    return [
        rows[i]
        for i in sorted(range(len(rows)), key=lambda i: -(1 / (60 + i) + weight / (60 + ranks[i])))
    ]


def run(request):
    rows = request["rows"]
    if request["mode"] == "vector":
        return list(range(len(rows)))
    ranked = rerank(
        [{**row, "_position": i} for i, row in enumerate(rows)], request["query"], request["weight"]
    )
    return [row["_position"] for row in ranked]
