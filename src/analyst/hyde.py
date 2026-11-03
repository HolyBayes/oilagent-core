"""Cached search probes; only real PDF passages may become evidence."""

import json
import os
import sqlite3
from contextlib import closing
from contextvars import ContextVar
from itertools import zip_longest

import numpy as np
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from analyst.config import CORE_ROOT, invoke_structured, model_timeout
from analyst.releases import sha


class SearchRepresentations(BaseModel):
    """Untrusted search representations; never PDF evidence."""

    english_query: str = Field(min_length=1, max_length=1600)
    alternative_query: str = Field(min_length=1, max_length=1600)
    hypothetical_document: str = Field(min_length=1, max_length=1600)


# Only the protected evaluator supplies this offline replay hook.
replay_probes = ContextVar("rag_replay_probes", default=None)


def hyde_enabled():
    load_dotenv(CORE_ROOT / ".env", override=False)
    value = os.getenv("RAG_HYDE_ENABLED", "true").lower()
    if value not in {"true", "false"}:
        raise ValueError("RAG_HYDE_ENABLED must be true or false")
    return value == "true"


def generate_probes(query, prompt, directory, *, model=None):
    load_dotenv(CORE_ROOT / ".env", override=False)
    if not query.strip() or len(query) > 4000:
        raise ValueError("HyDE query must contain 1–4000 characters")
    provider = os.getenv("RAG_HYDE_PROVIDER", "gigachat")
    model = model or os.getenv("RAG_HYDE_MODEL", "GigaChat-2")
    if provider not in {"gigachat", "openai", "local"} or not model.strip():
        raise ValueError("Configure RAG_HYDE_PROVIDER and RAG_HYDE_MODEL")
    key = sha(
        json.dumps(
            [
                prompt,
                query,
                provider,
                model,
                os.getenv("LLM_BASE_URL", "") if provider != "gigachat" else "",
                os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS") if provider == "gigachat" else "",
                os.getenv("LLM_STRUCTURED_METHOD", "function_calling"),
            ]
        ).encode()
    )
    replay = replay_probes.get()
    if replay is not None:
        return SearchRepresentations.model_validate(
            replay(query, prompt, provider, model)
        ).model_dump()
    directory.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(directory / "hyde.sqlite3", timeout=model_timeout())) as cache,
        cache,
    ):
        cache.execute("CREATE TABLE IF NOT EXISTS expansions (key TEXT PRIMARY KEY, payload TEXT)")
        # Serialize cache misses across processes to avoid duplicate paid calls.
        cache.execute("BEGIN IMMEDIATE")
        hit = cache.execute("SELECT payload FROM expansions WHERE key = ?", (key,)).fetchone()
        if hit:
            return SearchRepresentations.model_validate_json(hit[0]).model_dump()
        passage, _ = invoke_structured(
            SearchRepresentations,
            [("system", prompt), ("human", query)],
            provider=provider,
            model=model,
        )
        cache.execute("INSERT INTO expansions VALUES (?, ?)", (key, passage.model_dump_json()))
        return passage.model_dump()


def weighted_embedding(probes, embedder):
    vectors = embedder.encode(
        [p["kind"] + ": " + p["text"] for p in probes],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    vector = np.average(np.asarray(vectors), axis=0, weights=[p["weight"] for p in probes])[None, :]
    norm = np.linalg.norm(vector)
    if not np.isfinite(vector).all() or not np.isfinite(norm) or norm == 0:
        raise ValueError("Invalid query embedding")
    return (vector / norm).tolist()


def strategy_search(index, query, *, top_k, include_context, policy, publishers, model=None):
    from analyst.contracts import RetrievalPolicy
    from analyst.method_contracts import validate
    from analyst.method_runtime import run
    from analyst.rag import report_publishers
    from analyst.releases import active_release

    if not query.strip() or len(query) > 4000:
        raise ValueError("Search query must contain 1–4000 characters")
    policy = RetrievalPolicy.model_validate(policy or active_release()["policy"])
    source = index.query_source

    def execute(request):
        return validate("query_strategy", request, run("query_strategy", request, source))

    prompt = execute({"phase": "plan", "query": query})["prompt"]
    generated = generate_probes(query, prompt, index.directory, model=model) if prompt else {}
    plan = execute({"phase": "expand", "query": query, "generated": generated})
    # Agency scope comes from the original question, never a generated search probe.
    scope = publishers or report_publishers(query) or [None]
    candidates, rows = [], []
    for search in plan["searches"]:
        vector = weighted_embedding(search["probes"], index.model())
        hits = index.search(
            search["query"],
            top_k=top_k,
            include_context=include_context,
            policy=policy.model_dump(),
            publishers=scope,
            _query_vector=vector,
        )
        for rank, row in enumerate(hits):
            candidates.append(row)
            rows.append(
                {
                    "doc_id": row["doc_id"],
                    "page": row["page"],
                    "publisher": row["publisher"],
                    "rank": rank,
                    "weight": search["weight"],
                }
            )
    order = execute({"phase": "fuse", "rows": rows, "fusion_k": plan["fusion_k"]})
    seen, pools = set(), {}
    for position in order:
        row = candidates[position]
        key = (row["doc_id"], row["page"])
        pool = pools.setdefault(row["publisher"], [])
        if key not in seen and len(pool) < min(top_k, policy.top_k_per_publisher):
            seen.add(key)
            pool.append(row)
    limit = min(top_k, policy.top_k_per_publisher) if policy.comparison_strategy == "pooled" else 12
    selected = [r for group in zip_longest(*pools.values()) for r in group if r is not None][:limit]
    return [{**row, "source_id": f"R{i}"} for i, row in enumerate(selected, 1)]
