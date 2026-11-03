"""HyDE query expansion and page-level reciprocal-rank fusion."""

PROMPT = (
    "Produce search representations for this oil/gas question. Preserve agency, publication "
    "date, forecast period, geography and units. english_query is a concise English translation; "
    "alternative_query uses other relevant English technical terms. hypothetical_document is "
    "an English hypothetical report paragraph, at most 90 words, with unknown numeric values "
    "represented by [VALUE]. It is only a retrieval probe, never evidence. Do not claim you "
    "have read a report or add another year or agency."
)


def run(request):
    if request["phase"] == "plan":
        return {"prompt": PROMPT}
    if request["phase"] == "expand":
        query = request["query"]
        passage = request["generated"]["hypothetical_document"]
        return {
            "searches": [
                {
                    "query": query,
                    "weight": 1.0,
                    "probes": [
                        {"text": query, "kind": "query", "weight": 1.0},
                        {"text": passage, "kind": "passage", "weight": 1.0},
                    ],
                }
            ],
            "fusion_k": 60,
        }
    scores = {}
    for row in request["rows"]:
        key = (row["doc_id"], row["page"])
        scores[key] = scores.get(key, 0) + row["weight"] / (request["fusion_k"] + row["rank"])
    return sorted(
        range(len(request["rows"])),
        key=lambda i: -scores[(request["rows"][i]["doc_id"], request["rows"][i]["page"])],
    )
