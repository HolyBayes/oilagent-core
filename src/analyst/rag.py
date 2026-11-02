import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from itertools import zip_longest

from analyst.config import CORE_ROOT, configured_path
from analyst.ranking import query_passages, rerank


def digest(data):
    return hashlib.sha256(data).hexdigest()


def page_chunks(text, tokenizer, size=400, overlap=60):
    offsets = tokenizer(
        text, add_special_tokens=False, return_offsets_mapping=True, truncation=False, verbose=False
    )["offset_mapping"]
    for start in range(0, len(offsets), size - overlap):
        window = offsets[start : start + size]
        yield text[window[0][0] : window[-1][1]], window[0][0]
        if start + size >= len(offsets):
            break


@lru_cache(maxsize=1)
def embedding_model(model, revision, cache):
    from sentence_transformers import SentenceTransformer

    snapshot = cache / ("models--" + model.replace("/", "--")) / "snapshots" / revision
    return SentenceTransformer(
        model,
        revision=revision,
        device="cpu",
        cache_folder=str(cache),
        local_files_only=snapshot.is_dir(),
    )


class ReportIndex:
    def __init__(self, manifest=None, directory=None, reports_dir=None, embedder=None):
        self.manifest = manifest or configured_path("REPORT_MANIFEST_PATH", "data/reports.json")
        self.directory = directory or configured_path("RAG_INDEX_PATH", "workspace/rag")
        self.reports_dir = reports_dir or configured_path("REPORTS_PATH", "workspace/reports")
        self.embedding = json.loads((CORE_ROOT / "config/embedding.json").read_text())
        self.embedder = embedder

    def model(self):
        if self.embedder is None:
            self.embedder = embedding_model(
                self.embedding["model"],
                self.embedding["revision"],
                configured_path("EMBEDDING_CACHE_PATH", "workspace/models"),
            )
        return self.embedder

    def collection(self, name, create=False):
        import chromadb

        client = chromadb.PersistentClient(path=str(self.directory))
        if create:
            return client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}, embedding_function=None
            )
        return client.get_collection(name=name, embedding_function=None)

    def download(self):
        import httpx

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        for report in json.loads(self.manifest.read_text())["reports"]:
            path = self.reports_dir / f"{report['doc_id']}.pdf"
            if path.exists():
                if digest(path.read_bytes()) != report["sha256"]:
                    raise ValueError(f"PDF hash mismatch: {report['doc_id']}")
                continue
            # URLs are operator-owned manifest entries, not model-generated links.
            with httpx.Client(timeout=45, follow_redirects=True) as client:
                response = client.get(report["url"])
                response.raise_for_status()
            data = response.content
            if not data.startswith(b"%PDF-") or digest(data) != report["sha256"]:
                raise ValueError(f"Unexpected PDF snapshot: {report['doc_id']}")
            path.write_bytes(data)

    def ingest(self):
        import pymupdf

        manifest = json.loads(self.manifest.read_text())
        identity = digest(json.dumps([manifest, self.embedding, 400, 60], sort_keys=True).encode())
        for report in manifest["reports"]:
            path = self.reports_dir / f"{report['doc_id']}.pdf"
            if digest(path.read_bytes()) != report["sha256"]:
                raise ValueError(f"PDF hash mismatch: {report['doc_id']}")
        name = f"reports_{identity[:20]}"
        collection = self.collection(name, create=True)
        pointer = self.directory / "index.json"
        if pointer.exists():
            current = json.loads(pointer.read_text())
            if current["corpus_hash"] == identity and collection.count() == current["chunks"]:
                return current
        model = self.model()
        chunks, warnings = [], []
        for report in manifest["reports"]:
            with pymupdf.open(self.reports_dir / f"{report['doc_id']}.pdf") as pdf:
                for number, page in enumerate(pdf, 1):
                    text = " ".join(page.get_text("text", sort=True).split())
                    if len(text) < 30:
                        warnings.append(f"empty_page:{report['doc_id']}:{number}")
                        continue
                    for text_part, offset in page_chunks(text, model.tokenizer):
                        chunks.append(
                            {
                                "id": f"{report['sha256']}:{number}:{offset}",
                                "text": text_part,
                                "metadata": {
                                    **{
                                        k: report[k]
                                        for k in [
                                            "doc_id",
                                            "title",
                                            "publisher",
                                            "published_at",
                                            "url",
                                            "sha256",
                                        ]
                                    },
                                    "page": number,
                                    "offset": offset,
                                    "numeric_verified": number in report["verified_numeric_pages"],
                                },
                            }
                        )
        for start in range(0, len(chunks), 64):
            batch = chunks[start : start + 64]
            vectors = model.encode(
                ["passage: " + c["text"] for c in batch],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            collection.upsert(
                ids=[c["id"] for c in batch],
                embeddings=vectors.tolist(),
                documents=[c["text"] for c in batch],
                metadatas=[c["metadata"] for c in batch],
            )
        result = {
            "collection": name,
            "corpus_hash": identity,
            "embedding": self.embedding,
            "chunks": len(chunks),
            "warnings": warnings,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        temp = pointer.with_suffix(".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        temp.replace(pointer)
        return result

    def search(self, query, top_k=4, *, include_context=True, policy=None, publishers=None):
        if not 1 <= top_k <= 12:
            raise ValueError("top_k must be between 1 and 12")
        pointer = self.directory / "index.json"
        if not pointer.exists():
            return []
        index = json.loads(pointer.read_text())
        if index["embedding"] != self.embedding:
            raise ValueError("Embedding revision changed; reindex reports")
        collection = self.collection(index["collection"])
        if collection.count() == 0:
            return []
        vector = (
            self.model()
            .encode(["query: " + query], normalize_embeddings=True, show_progress_bar=False)
            .tolist()
        )
        publishers = (
            publishers
            or [
                p
                for p, pattern in [("OPEC", r"\bOPEC\b|ОПЕК"), ("EIA", r"\bEIA\b")]
                if re.search(pattern, query, re.I)
            ]
            or [None]
        )
        if policy is None:
            from analyst.releases import active_release

            policy = active_release()["policy"]
        from analyst.contracts import RetrievalPolicy

        policy = RetrievalPolicy.model_validate(policy)
        if policy.comparison_strategy == "pooled":
            publishers = [None]
        selection_k = min(top_k, policy.top_k_per_publisher)
        ranked = []
        for publisher in publishers:
            where = {"publisher": publisher} if publisher else None
            result = collection.query(
                query_embeddings=vector,
                n_results=collection.count()
                if policy.reranker == "bm25"
                else min(top_k * 3, collection.count()),
                where=where,
            )
            pages, rows = set(), []
            candidates = []
            for cid, text, meta, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            ):
                candidates.append({**meta, "chunk_id": cid, "text": text, "distance": distance})
            if policy.reranker == "bm25":
                candidates = rerank(candidates, query, weight=policy.lexical_weight)
            for candidate in candidates:
                meta = candidate
                page = (meta["doc_id"], meta["page"])
                if page not in pages:
                    rows.append(candidate)
                    pages.add(page)
            ranked.append(rows[:selection_k])
        # Interleave publishers before the shared context budget is applied.
        rows = [row for pair in zip_longest(*ranked) for row in pair if row is not None][:12]
        if include_context:
            for row in rows:
                if not row.get("offset"):
                    continue
                intro = collection.get(
                    where={
                        "$and": [{"doc_id": row["doc_id"]}, {"page": row["page"]}, {"offset": 0}]
                    }
                )
                if intro["ids"]:
                    text = intro["documents"][0]
                    row["page_intro"] = text[:800].rsplit(" ", 1)[0] if len(text) > 800 else text
                    row["intro_chunk_id"] = intro["ids"][0]
        if include_context and policy.page_expansion == "query":
            for row in rows:
                page = collection.get(
                    where={"$and": [{"doc_id": row["doc_id"]}, {"page": row["page"]}]}
                )
                chunks = sorted(
                    zip(page["metadatas"], page["documents"]), key=lambda item: item[0]["offset"]
                )
                text = ""
                for metadata, part in chunks:
                    offset = metadata["offset"]
                    if offset > len(text):
                        raise ValueError("Missing page chunk")
                    text = text[:offset] + part
                row["support_spans"] = query_passages(text, query)
                row["context_chunk_ids"] = page["ids"]
        return [{**row, "source_id": f"R{i}"} for i, row in enumerate(rows, 1)]
