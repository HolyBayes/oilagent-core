"""Compare retrieval approaches on fixed questions; --generate allows paid cached rewrites."""

import argparse
import hashlib
import json
import os
import time
from itertools import zip_longest

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from analyst.capabilities import trusted_evaluation
from analyst.code_packages import SLOTS, artifact
from analyst.code_releases import read_bundle
from analyst.config import CORE_ROOT, invoke_structured
from analyst.evidence import fit_context
from analyst.method_runtime import code_root, method_pin
from analyst.quality import supported
from analyst.rag import ReportIndex, report_publishers

PROMPT = (
    "Produce search representations for this oil/gas question. Preserve agency, publication "
    "date, forecast period, geography and units. english_query is a concise English translation; "
    "alternative_query uses other relevant English technical terms. hypothetical_document is "
    "an English hypothetical report paragraph, at most 90 words, with unknown numeric values "
    "represented by [VALUE]. It is only a retrieval probe, never evidence. Do not claim you "
    "have read a report or add another year or agency."
)


class Variants(BaseModel):
    """Search-only query variants and an untrusted hypothetical report passage."""

    english_query: str = Field(min_length=1, max_length=1600)
    alternative_query: str = Field(min_length=1, max_length=1600)
    hypothetical_document: str = Field(min_length=1, max_length=1600)


def fuse(lists):
    scores, rows = {}, {}
    for weight, items in lists:
        seen = set()
        for rank, row in enumerate(items):
            key = (row["doc_id"], row["page"])
            if key in seen:
                continue
            seen.add(key)
            rows.setdefault(key, row)
            scores[key] = scores.get(key, 0) + weight / (60 + rank)
    ranked = sorted(rows, key=lambda key: -scores[key])
    publishers = list(dict.fromkeys(rows[k]["publisher"] for k in ranked))
    pools = [[rows[k] for k in ranked if rows[k]["publisher"] == pub][:4] for pub in publishers]
    merged = [r for group in zip_longest(*pools) for r in group if r is not None][:12]
    return [{**row, "source_id": f"R{i}"} for i, row in enumerate(merged, 1)]


class FixedEmbedding:
    def __init__(self, vector):
        self.vector = vector

    def encode(self, texts, **kwargs):
        return self.vector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--only-generate", action="store_true")
    args = parser.parse_args()
    load_dotenv(CORE_ROOT / ".env", override=False)
    cases = [
        c
        for c in json.loads((CORE_ROOT / "data/acceptance_cases.json").read_text())["cases"]
        if c["kind"] == "retrieval"
    ]
    cache = CORE_ROOT / "workspace/rag-queries"
    cache.mkdir(parents=True, exist_ok=True)
    variants = {}
    provider = os.getenv("LLM_PROVIDER", "gigachat")
    model_id = (
        os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        if provider == "gigachat"
        else os.getenv("LLM_MODEL", "")
    )
    model_key = provider + model_id + os.getenv("LLM_BASE_URL", "")
    for case in cases:
        key = hashlib.sha256((PROMPT + model_key + case["question"]).encode()).hexdigest()
        path = cache / (key + ".json")
        if not path.exists() and args.generate:
            result, usage = invoke_structured(
                Variants, [("system", PROMPT), ("human", case["question"])]
            )
            path.write_text(
                json.dumps(
                    {
                        "query": case["question"],
                        "variants": result.model_dump(),
                        "usage": usage,
                        "model": model_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            print("generated", case["case_id"], usage.get("total_tokens"), flush=True)
        if path.exists():
            variants[case["case_id"]] = json.loads(path.read_text())
    if args.only_generate:
        return
    release_id = json.loads((code_root() / "active.json").read_text())["release_id"]
    bundle = read_bundle(release_id, historical=True)
    method_pin.set({slot: bundle["files"][artifact(slot)] for slot in SLOTS})
    index = ReportIndex()
    model = index.model()

    def retrieve(query, mode, vector=None):
        policy = {
            "comparison_strategy": "per_publisher",
            "top_k_per_publisher": 4,
            "reranker": mode,
            "lexical_weight": 1.0,
            "page_expansion": "query",
        }
        target = index if vector is None else ReportIndex(embedder=FixedEmbedding(vector))
        return target.search(query, policy=policy, publishers=source_scope)

    strategies = [
        "vector",
        "hybrid",
        "multiquery_vector",
        "multiquery_hybrid",
        "hyde_vector",
        "hyde_hybrid",
    ]
    records = []
    for case in cases:
        source_scope = report_publishers(case["question"]) or [None]
        variant = variants.get(case["case_id"])
        for strategy in strategies:
            if strategy not in {"vector", "hybrid"} and variant is None:
                continue
            started = time.monotonic()
            mode = "bm25" if strategy.endswith("hybrid") else "vector"
            query = case["question"]
            if strategy.startswith("multiquery"):
                v = variant["variants"]
                rows = fuse(
                    [
                        (2.0, retrieve(query, mode)),
                        (1.0, retrieve(v["english_query"], mode)),
                        (1.0, retrieve(v["alternative_query"], mode)),
                    ]
                )
            elif strategy.startswith("hyde"):
                text = variant["variants"]["hypothetical_document"]
                vectors = model.encode(
                    ["query: " + query, "passage: " + text],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                vector = np.asarray(vectors).mean(axis=0, keepdims=True)
                vector /= np.linalg.norm(vector)
                rows = retrieve(query, mode, vector)
            else:
                rows = retrieve(query, mode)
            selected = fit_context(rows, query)
            records.append(
                {
                    "case": case["case_id"],
                    "strategy": strategy,
                    "retrieved": supported(case, rows),
                    "in_context": supported(case, selected),
                    "seconds": time.monotonic() - started,
                }
            )
        print("measured", case["case_id"], flush=True)
        summary = {
            s: {
                "retrieved": sum(r["retrieved"] for r in records if r["strategy"] == s),
                "in_context": sum(r["in_context"] for r in records if r["strategy"] == s),
                "total": sum(r["strategy"] == s for r in records),
                "seconds": round(sum(r["seconds"] for r in records if r["strategy"] == s), 2),
            }
            for s in strategies
        }
        output = {
            "scope": "Fixed seen queries, not a blind benchmark; generated text is never evidence",
            "method_release_id": release_id,
            "summary": summary,
            "cases": records,
            "generation_usage": {
                k: sum(v.get("usage", {}).get(k, 0) for v in variants.values())
                for k in ["input_tokens", "output_tokens", "total_tokens"]
            },
        }
        (CORE_ROOT / "workspace/rag-benchmark.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    with trusted_evaluation():
        main()
