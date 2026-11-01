import re

from analyst.contracts import ReportDraft


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
            or claim.quote not in source["text"]
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
