import hashlib
import json
import re

import numpy as np
import pymupdf
import pytest

from analyst import graph as pipeline
from analyst.contracts import ReportClaim, ReportDraft, Route
from analyst.evidence import render_answer, validate_claims
from analyst.rag import ReportIndex, digest, page_chunks


class Embeddings:
    calls = 0

    def tokenizer(self, text, **kwargs):
        return {"offset_mapping": [m.span() for m in re.finditer(r"\S+", text)]}

    def encode(self, texts, **kwargs):
        self.calls += 1
        vectors = np.zeros((len(texts), 32))
        for i, text in enumerate(texts):
            for word in text.lower().split()[1:]:
                vectors[i, hashlib.sha256(word.encode()).digest()[0] % 32] += 1
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1)


@pytest.fixture
def index(tmp_path):
    reports = []
    for publisher in ["EIA", "OPEC"]:
        path = tmp_path / f"{publisher}.pdf"
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40, 50), f"{publisher} forecast Brent price is 52 in 2026.")
            pdf.new_page()  # Scans without extractable text must be visible in ingestion warnings.
            pdf.save(path)
        reports.append(
            {
                "doc_id": publisher,
                "publisher": publisher,
                "title": f"{publisher} outlook",
                "url": f"https://example.org/{publisher}.pdf",
                "published_at": "2025-10-07",
                "sha256": digest(path.read_bytes()),
                "verified_numeric_pages": [1],
            }
        )
    manifest = tmp_path / "reports.json"
    manifest.write_text(json.dumps({"reports": reports}))
    return ReportIndex(manifest, tmp_path / "index", tmp_path, Embeddings())


def test_pdf_ingest_provenance_persistence_and_cache(index):
    result = index.ingest()
    assert result["chunks"] == 2
    assert result["warnings"] == ["empty_page:EIA:2", "empty_page:OPEC:2"]
    calls = index.model().calls
    assert index.ingest() == result
    assert index.model().calls == calls
    reopened = ReportIndex(index.manifest, index.directory, index.reports_dir, Embeddings())
    rows = reopened.search("Compare EIA and OPEC Brent forecasts", 12)
    assert {r["publisher"] for r in rows} == {"EIA", "OPEC"}
    assert all(r["page"] == 1 and r["numeric_verified"] for r in rows)
    assert len({r["chunk_id"] for r in rows}) == len(rows)
    assert all(r["text"] in f"{r['publisher']} forecast Brent price is 52 in 2026." for r in rows)


def test_missing_index_hash_mismatch_and_embedding_drift(index):
    assert index.search("oil") == []
    index.ingest()
    index.embedding = {"model": "changed", "revision": "changed"}
    with pytest.raises(ValueError, match="reindex"):
        index.search("oil")
    (index.reports_dir / "EIA.pdf").write_bytes(b"altered PDF")
    with pytest.raises(ValueError, match="hash mismatch"):
        index.ingest()


def test_neighboring_chunks_do_not_crowd_out_other_pages(index):
    info = index.ingest()
    collection = index.collection(info["collection"])
    collection.delete(ids=collection.get()["ids"])
    query = "EIA Brent price"
    vector = index.model().encode(["query: " + query])[0]
    other = vector.copy()
    other[0] += 0.5
    metadata = {"publisher": "EIA", "doc_id": "EIA", "page": 1}
    collection.upsert(
        ids=["neighbor1", "neighbor2", "next_page"],
        documents=["neighbor one", "neighbor two", "different page"],
        embeddings=[vector.tolist(), vector.tolist(), other.tolist()],
        metadatas=[metadata, metadata, metadata | {"page": 2}],
    )
    rows = index.search(query, 2)
    assert {r["page"] for r in rows} == {1, 2}


def test_chunks_cover_text_with_token_overlap():
    text = " ".join(f"word{i}" for i in range(900))
    chunks = list(page_chunks(text, Embeddings().tokenizer))
    assert len(chunks) == 3
    assert chunks[0][0].endswith("word399")
    assert chunks[1][0].startswith("word340 ")
    assert chunks[-1][0].endswith("word899")
    assert all(text[offset : offset + len(part)] == part for part, offset in chunks)
    assert list(page_chunks("", Embeddings().tokenizer)) == []


@pytest.mark.parametrize(
    "changes,warning",
    [
        ({"source_id": "R99"}, "invalid_citation"),
        ({"quote": "invented quote"}, "invalid_citation"),
        ({"text": "Цена 100 в 2026 году"}, "unverified_number"),
        ({"text": "Цена 52 [R99]"}, "invalid_citation"),
        ({"text": "https://fake.org"}, "invalid_citation"),
    ],
)
def test_invalid_claims_are_removed(changes, warning):
    claim = {"text": "Цена 52 в 2026 году", "source_id": "R1", "quote": "Price 52 in 2026"}
    source = {"source_id": "R1", "text": "Price 52 in 2026", "numeric_verified": True}
    draft = ReportDraft(claims=[ReportClaim(**(claim | changes))], abstain=False)
    assert validate_claims(draft, [source]) == ([], [warning])


def test_graph_answer_and_numeric_gate(index, monkeypatch):
    index.ingest()
    monkeypatch.setattr(pipeline, "ReportIndex", lambda: index)
    monkeypatch.setattr(pipeline, "model_ready", lambda: True)

    def invoke(schema, messages):
        if schema is Route:
            return Route(intent="domain_qa", freshness_required=False), {"total_tokens": 10}
        evidence = json.loads(messages[1][1])["reports"][0]
        claim = ReportClaim(
            text="В отчёте прогнозируется Brent 52 в 2026 году.",
            source_id=evidence["source_id"],
            quote=evidence["text"],
        )
        return ReportDraft(claims=[claim], abstain=False), {"total_tokens": 20}

    monkeypatch.setattr(pipeline, "invoke_structured", invoke)
    answer = pipeline.answer_question("EIA Brent forecast")
    assert answer["status"] == "answered"
    assert "https://example.org/EIA.pdf#page=1" in answer["answer"]
    assert answer["usage"]["synthesis"]["total_tokens"] == 20
    answer["evidence"][0]["numeric_verified"] = False
    draft = ReportDraft(claims=answer["claims"], abstain=False)
    claims, warnings = validate_claims(draft, answer["evidence"])
    assert claims == [] and warnings == ["unverified_number"]
    assert "недостаточно" in render_answer(claims, answer["evidence"])


@pytest.mark.parametrize(
    "intent,freshness",
    [("out_of_scope", False), ("forecast", False), ("scenario", False), ("domain_qa", True)],
)
def test_unavailable_routes_skip_retrieval(intent, freshness, monkeypatch):
    monkeypatch.setattr(pipeline, "ReportIndex", lambda: pytest.fail("Unexpected retrieval"))
    state = {"route": {"intent": intent, "freshness_required": freshness}, "question": "test"}
    assert pipeline.retrieve(state) == {"evidence": []}
    assert pipeline.respond(state)["status"] != "answered"
