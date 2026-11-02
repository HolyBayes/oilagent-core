import json

from analyst import graph as pipeline
from analyst.contracts import ReportDraft


def test_report_query_is_same_in_standalone_and_combined_request():
    question = "Что EIA прогнозировало для Brent в первом полугодии 2026"
    assert pipeline.report_question({"question": question + "?", "route": {}}) == (
        pipeline.report_question(
            {
                "question": question + "; а затем добавь новости.",
                "route": {"report_query": "invalid translation"},
            }
        )
    )


def test_complete_synthesis_prompt_fits_and_marks_omitted_evidence(monkeypatch):
    captured = []

    def invoke(schema, messages):
        captured.append(messages)
        return ReportDraft(claims=[], abstain=True), {}

    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    payload = {"reports": [{"text": "a" * 4500} for _ in range(3)]}
    pipeline.synthesize([("system", "s" * 2500), ("human", json.dumps(payload))])
    assert sum(len(text) for _, text in captured[0]) <= 12000
    assert json.loads(captured[0][-1][1])["context_incomplete"]
