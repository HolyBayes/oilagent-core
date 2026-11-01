import json
import re

from analyst.contracts import ReportDraft


def fit_context(rows, question):
    selected, size = [], 0
    for row in rows:
        length = len(json.dumps(row, ensure_ascii=False))
        if size + length > 10000 - len(question):
            break
        selected.append(row)
        size += length
    return selected


def numbers(text):
    return {m.replace(",", ".") for m in re.findall(r"\d+(?:[.,]\d+)?", text)}


def validate_claims(draft: ReportDraft, evidence):
    sources = {e["source_id"]: e for e in evidence}
    accepted, warnings = [], []
    if draft.abstain:
        return [], ["insufficient_evidence"]
    for claim in draft.claims:
        source = sources.get(claim.source_id)
        if (
            not source
            or not claim.quote.strip()
            or not any(claim.quote in source.get(k, "") for k in ["text", "page_intro"])
            or re.search(r"https?://|\[(?:R|W)\d+\]", claim.text)
        ):
            warnings.append("invalid_citation")
        elif numbers(claim.text) and (
            not source["numeric_verified"] or not numbers(claim.text) <= numbers(claim.quote)
        ):
            warnings.append("unverified_number")
        else:
            accepted.append(claim.model_dump())
    return accepted, sorted(set(warnings))


def render_answer(claims, evidence):
    if not claims:
        return "В выбранных фрагментах недостаточно подтверждённых данных для ответа."
    used = {c["source_id"] for c in claims}
    lines = [f"{c['text']} [{c['source_id']}]" for c in claims]
    lines.append("\nИсточники:")
    lines.extend(
        f"[{s['source_id']}] {s['title']}, выпуск {s['published_at']}, "
        f"PDF стр. {s['page']}: {s['url']}#page={s['page']}"
        for s in evidence
        if s["source_id"] in used
    )
    return "\n\n".join(lines)
