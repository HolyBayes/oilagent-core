import json
import re
from decimal import Decimal

from analyst.contracts import ReportDraft
from analyst.measurements import comparable


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
    return {
        str(Decimal(m.replace(",", ".")).normalize())
        for m in re.findall(r"(?<!\d)[-+]\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", text.replace("−", "-"))
    }


def supporting_passages(source):
    return [source.get("text", ""), source.get("page_intro", ""), *source.get("support_spans", [])]


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
            or not any(claim.quote in text for text in supporting_passages(source))
            or re.search(r"https?://|\[(?:R|W)\d+\]", claim.text)
        ):
            warnings.append("invalid_citation")
        elif numbers(claim.text) and (
            not source["numeric_verified"] or not numbers(claim.text) <= numbers(claim.quote)
        ):
            warnings.append("unverified_number")
        elif (
            source.get("kind") == "web"
            and numbers(claim.text)
            and re.search(
                r"\b(?:сейчас|сегодня|актуальн\w*|текущ\w*|today|current\w*|now|live)\b",
                claim.text,
                re.I,
            )
        ):
            warnings.append("unverified_live_fact")
        else:
            if claim.value and (
                not numbers(claim.value) <= numbers(claim.quote)
                or not claim.unit
                or not claim.period
            ):
                warnings.append("invalid_measurement")
            else:
                accepted.append(claim.model_dump())
    return accepted, sorted(set(warnings))


def compare_claims(claims):
    measured = [c for c in claims if c.get("value") and c.get("kind", "fact") == "fact"]
    if len(measured) != 2:
        return None, "comparison_missing_two_measurements"
    a, b = measured
    fields = ("metric", "geography", "unit", "period", "vintage", "observation_type")
    if a["source_id"] == b["source_id"] or any(not a.get(k) or not b.get(k) for k in fields):
        return None, "comparison_incompatible_definitions"
    if a["observation_type"] == "unspecified":
        return None, "comparison_unspecified_observation_type"
    try:
        normalized_a, normalized_b = comparable(a), comparable(b)
        if any(normalized_a[k] != normalized_b[k] for k in fields):
            return None, "comparison_incompatible_definitions"
        difference = normalized_a["value"] - normalized_b["value"]
        if not difference.is_finite():
            raise ValueError("Nonfinite difference")
    except Exception:
        return None, "comparison_invalid_values"
    return {
        "kind": "calculation",
        "formula": "a-b",
        "inputs": [a, b],
        "value": str(difference),
        "unit": "percentage points" if normalized_a["unit"] == "percent" else normalized_a["unit"],
        "period": normalized_a["period"],
        "normalized_inputs": [
            {**normalized_a, "value": str(normalized_a["value"])},
            {**normalized_b, "value": str(normalized_b["value"])},
        ],
    }, ""


def render_answer(claims, evidence):
    if not claims:
        return "В выбранных фрагментах недостаточно подтверждённых данных для ответа."
    used = {c["source_id"] for c in claims}
    lines = [f"{c['text']} [{c['source_id']}]" for c in claims]
    lines.append("\nИсточники:")
    lines.extend(
        (
            f"[{s['source_id']}] web, {s['publisher']}: {s['title']}, "
            f"публикация {s['published_at'] or 'дата неизвестна'}, "
            f"получено {s['retrieved_at']}: {s['url']}"
            if s.get("kind") == "web"
            else f"[{s['source_id']}] {s['title']}, выпуск {s['published_at']}, "
            f"PDF стр. {s['page']}: {s['url']}#page={s['page']}"
        )
        for s in evidence
        if s["source_id"] in used
    )
    return "\n\n".join(lines)


def rejection_details(draft, evidence):
    sources = {e["source_id"]: e for e in evidence}
    details = []
    for claim in draft.claims:
        source = sources.get(claim.source_id)
        if not source:
            details.append({"source_id": claim.source_id, "reason": "unknown_source_id"})
            continue
        if not any(claim.quote in text for text in supporting_passages(source)):
            details.append(
                {
                    "source_id": claim.source_id,
                    "reason": "quote_not_verbatim; copy a contiguous span exactly",
                }
            )
        if re.search(r"https?://|\[(?:R|W)\d+\]", claim.text):
            details.append(
                {
                    "source_id": claim.source_id,
                    "reason": "remove URLs and [R/W] markers from text; renderer adds them",
                }
            )
        missing = numbers(claim.text) - numbers(claim.quote)
        if missing:
            details.append(
                {
                    "source_id": claim.source_id,
                    "reason": "numbers absent from quote",
                    "unsupported_numbers": sorted(missing),
                }
            )
        if numbers(claim.text) and not source.get("numeric_verified"):
            details.append(
                {"source_id": claim.source_id, "reason": "numeric claims prohibited on this page"}
            )
    return details
