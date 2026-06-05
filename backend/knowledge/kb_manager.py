"""
KB Manager — Hybrid RAG: Dense + BM25 + Graph (entity index) fused via RRF.

Collections:
  kb_collection    — policy/FAQ chunks
  calls_collection — past call transcript chunks (customer_id tagged)

Retrieval pipeline:
  1. Dense   — ChromaDB cosine (all-MiniLM-L6-v2, 384-dim, local)
  2. BM25    — BM25Okapi in-memory (rank-bm25)
  3. Graph   — entity inverted index (regex, zero LLM cost)
  4. RRF     — Reciprocal Rank Fusion, k=60, top-N final result
"""
import re
import uuid
import logging
import numpy as np
from pathlib import Path
from typing import Optional

from knowledge.document_parser import parse_and_chunk, extract_headings, TOKENIZER
from knowledge.embeddings import embed_texts, embed_single

logger = logging.getLogger(__name__)

# ── Module state ──────────────────────────────────────────────────────────────

_kb_collection = None
_calls_collection = None
_collections: dict = {}   # name → ChromaDB collection object

_bm25_index = None
_bm25_corpus: list[dict] = []                      # [{id, text, metadata}]
_entity_index: dict[str, list[str]] = {}           # entity → [chunk_id, ...]
_entity_pair_index: dict[str, list[str]] = {}      # "e1+e2" → [chunk_id, ...] (sorted, multi-hop)
_doc_headings: dict[str, list[str]] = {}           # doc_id → [heading, ...]

CALL_DISTANCE_THRESHOLD = 0.5

# ── Entity patterns for Graph RAG lite ───────────────────────────────────────

_ENTITY_PATTERNS = [
    re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b'),        # CamelCase: LiveKit, Pipecat
    re.compile(r'\$[\d,]+(?:\.\d{2})?'),                    # $5.00, $100
    re.compile(r'\b\d+\s*(?:days?|hours?|minutes?|weeks?)\b', re.I),  # 30 days
    re.compile(r'(?:Section|Article|Clause)\s+[\d.]+', re.I),         # Section 5.2
    re.compile(r'\b\d+(?:\.\d+)?%'),                        # 15%, 3.5%
]


def _extract_entities(text: str) -> list[str]:
    entities = set()
    for pattern in _ENTITY_PATTERNS:
        for match in pattern.findall(text):
            entities.add(match.lower().strip())
    return list(entities)


# ── Init ──────────────────────────────────────────────────────────────────────

def init_kb_manager(kb_col, calls_col, _openai_client=None, collections_dict: dict | None = None) -> None:
    global _kb_collection, _calls_collection, _collections
    _kb_collection = kb_col
    _calls_collection = calls_col
    if collections_dict:
        _collections = collections_dict
    # Always register the default collection by name
    if kb_col is not None:
        _collections.setdefault("kb_collection", kb_col)
    _rebuild_indexes()


# ── Index rebuild (BM25 + entity) ────────────────────────────────────────────

def _rebuild_indexes() -> None:
    global _bm25_index, _bm25_corpus, _entity_index, _entity_pair_index
    if _kb_collection is None:
        return
    try:
        from rank_bm25 import BM25Okapi

        # Gather chunks from ALL registered collections so BM25 + entity
        # index covers every uploaded document regardless of which collection it lives in.
        all_cols = list(_collections.values()) if _collections else [_kb_collection]
        seen_ids: set[str] = set()
        ids, docs, metas = [], [], []
        for col in all_cols:
            results = col.get(include=["documents", "metadatas"])
            for i, d, m in zip(
                results.get("ids") or [],
                results.get("documents") or [],
                results.get("metadatas") or [],
            ):
                if i not in seen_ids:
                    seen_ids.add(i)
                    ids.append(i); docs.append(d); metas.append(m)

        _bm25_corpus = [{"id": i, "text": d, "metadata": m}
                        for i, d, m in zip(ids, docs, metas)]

        if docs:
            tokenized = [d.lower().split() for d in docs]
            _bm25_index = BM25Okapi(tokenized)
        else:
            _bm25_index = None

        # Entity inverted index + pair index (multi-hop, LightRAG-lite)
        _entity_index = {}
        _entity_pair_index = {}
        for chunk_id, doc in zip(ids, docs):
            entities = _extract_entities(doc)
            for entity in entities:
                _entity_index.setdefault(entity, []).append(chunk_id)
            # Store all co-occurring entity pairs — enables multi-hop retrieval
            # e.g. chunk has both "dashpass" + "refund" → "dashpass+refund" → chunk_id
            sorted_entities = sorted(set(entities))
            for i in range(len(sorted_entities)):
                for j in range(i + 1, len(sorted_entities)):
                    pair_key = f"{sorted_entities[i]}+{sorted_entities[j]}"
                    _entity_pair_index.setdefault(pair_key, []).append(chunk_id)

        logger.info(
            f"Indexes rebuilt: {len(docs)} chunks, "
            f"{len(_entity_index)} entities, {len(_entity_pair_index)} entity pairs"
        )
    except Exception as e:
        logger.error(f"Index rebuild failed: {e}")


# ── RRF fusion ────────────────────────────────────────────────────────────────

def _rrf_fusion(
    hit_lists: list[list[dict]],
    k: int = 60,
    n: int = 3,
    k_per_list: list[int] | None = None,
) -> list[dict]:
    """
    hit_lists: each inner list is a ranked list of hits.
    Each hit must have "chunk_id". Optional: via_dense, via_bm25, via_entity.
    k_per_list: per-list k override — lower k = higher contribution for same rank.
                Entity hits use k=40 (~1.5× boost) to reflect their precision advantage.
    Returns top-n by RRF score with retrieval attribution.
    """
    scores: dict[str, float] = {}
    registry: dict[str, dict] = {}

    for list_idx, hits in enumerate(hit_lists):
        effective_k = (k_per_list[list_idx] if k_per_list and list_idx < len(k_per_list) else k)
        for rank, h in enumerate(hits):
            cid = h["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (effective_k + rank + 1)
            if cid not in registry:
                registry[cid] = dict(h)
            else:
                # Merge attribution flags
                for flag in ("via_dense", "via_bm25", "via_entity"):
                    if h.get(flag):
                        registry[cid][flag] = True

    top_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:n]
    results = []
    for cid in top_ids:
        h = registry[cid]
        via_dense = h.get("via_dense", False)
        via_bm25 = h.get("via_bm25", False)
        via_entity = h.get("via_entity", False)

        if via_dense and (via_bm25 or via_entity):
            retrieval = "hybrid"
        elif via_dense:
            retrieval = "dense"
        elif via_entity:
            retrieval = "graph"
        else:
            retrieval = "bm25"

        results.append({
            **h,
            "rrf_score": round(scores[cid], 4),
            "retrieval": retrieval,
        })
    return results


# ── Upload & Index ────────────────────────────────────────────────────────────

async def ingest_document(
    file_path: str | Path,
    filename: str,
    file_type: str,
    category: str = "general",
    doc_id: str | None = None,
    collection_name: str | None = None,
) -> tuple[str, int]:
    # Use named collection if specified; fall back to default kb_collection
    target_col = _kb_collection
    if collection_name and collection_name in _collections:
        target_col = _collections[collection_name]
    if target_col is None:
        raise RuntimeError("kb_manager not initialized")

    doc_id = doc_id or str(uuid.uuid4())
    logger.info(f"Ingesting {filename} (doc_id={doc_id})")

    text, chunks = parse_and_chunk(file_path)
    if not chunks:
        logger.warning(f"No chunks produced for {filename}")
        return doc_id, 0

    # Store headings for suggested questions
    headings = extract_headings(text)
    _doc_headings[doc_id] = headings
    logger.info(f"Extracted {len(headings)} headings from {filename}")

    embeddings = await embed_texts(chunks)

    ids = [f"{doc_id}__chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "doc_id": doc_id,
            "filename": filename,
            "file_type": file_type,
            "category": category,
            "chunk_index": i,
            "type": "kb",
        }
        for i in range(len(chunks))
    ]

    target_col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    logger.info(f"Stored {len(chunks)} chunks for {filename}")

    # Rebuild in-memory indexes
    _rebuild_indexes()

    return doc_id, len(chunks)


async def delete_document(doc_id: str) -> int:
    if _kb_collection is None:
        return 0
    all_cols = list(_collections.values()) if _collections else [_kb_collection]
    total = 0
    for col in all_cols:
        results = col.get(where={"doc_id": doc_id})
        ids = results.get("ids", [])
        if ids:
            col.delete(ids=ids)
            total += len(ids)
    _doc_headings.pop(doc_id, None)
    _rebuild_indexes()
    return total


# ── Query — hybrid RRF ────────────────────────────────────────────────────────

async def search_kb(
    query: str,
    n_results: int = 3,
    collections: list[str] | None = None,
) -> list[dict]:
    """
    Hybrid search: Dense + BM25 + Graph entity index, fused via RRF.
    No hard distance threshold — top-N by RRF score.

    collections: list of collection names to search. Defaults to
    get_config().kb_collections if not provided.
    """
    if _kb_collection is None:
        return []

    if collections is None:
        try:
            from config_loader import get_config
            collections = list(get_config().kb_collections)
        except Exception:
            collections = []

    # Resolve all ChromaDB collections to search — query every listed collection
    # that exists and has content, then merge dense hits before RRF fusion.
    active_cols = [_collections[name] for name in collections if name in _collections]
    if not active_cols:
        active_cols = [_kb_collection] if _kb_collection is not None else []
    if not active_cols:
        return []

    fetch_n = n_results * 3   # fetch more from each source before fusion

    # Dense: search each collection separately and merge (dedup by chunk_id)
    seen_chunk_ids: set[str] = set()
    dense_hits: list[dict] = []
    for col in active_cols:
        if col.count() == 0:
            continue
        for hit in await _search_dense(query, fetch_n, collection=col):
            if hit["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(hit["chunk_id"])
                dense_hits.append(hit)

    bm25_hits = _search_bm25(query, fetch_n)
    entity_hits = _search_entity(query, fetch_n)

    # Entity hits use k=40 (≈1.5× boost vs k=60) — precision-weighted per LightRAG findings
    fused = _rrf_fusion(
        [dense_hits, bm25_hits, entity_hits],
        k=60,
        n=n_results,
        k_per_list=[60, 60, 40],
    )

    return [
        {
            "content": h["content"],
            "source": h.get("source", h.get("metadata", {}).get("filename", "KB")),
            "category": h.get("metadata", {}).get("category", "general"),
            "relevance": h["rrf_score"],
            "rrf_score": h["rrf_score"],
            "retrieval": h["retrieval"],
            "doc_id": h.get("metadata", {}).get("doc_id", ""),
        }
        for h in fused
    ]


async def _search_dense(query: str, n: int, collection=None) -> list[dict]:
    col = collection if collection is not None else _kb_collection
    if col is None:
        return []
    embedding = await embed_single(query)
    try:
        results = col.query(
            query_embeddings=[embedding],
            n_results=min(n, max(1, col.count())),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning(f"Dense KB query failed: {exc}")
        return []

    hits = []
    ids_row   = results.get("ids", [[]])[0]          # always returned by ChromaDB
    docs_row  = results.get("documents", [[]])[0]
    metas_row = results.get("metadatas", [[]])[0]
    dists_row = results.get("distances", [[]])[0]
    for cid, doc, meta, dist in zip(ids_row, docs_row, metas_row, dists_row):
        hits.append({
            "chunk_id": cid,
            "content": doc,
            "metadata": meta,
            "source": meta.get("filename", "KB"),
            "cosine_distance": dist,
            "via_dense": True,
        })
    return hits


def _search_bm25(query: str, n: int) -> list[dict]:
    if _bm25_index is None or not _bm25_corpus:
        return []
    tokenized_query = query.lower().split()
    scores = _bm25_index.get_scores(tokenized_query)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
    hits = []
    for rank_idx in ranked:
        if scores[rank_idx] <= 0:
            continue
        entry = _bm25_corpus[rank_idx]
        hits.append({
            "chunk_id": entry["id"],
            "content": entry["text"],
            "metadata": entry["metadata"],
            "source": entry["metadata"].get("filename", "KB"),
            "bm25_score": float(scores[rank_idx]),
            "via_bm25": True,
        })
    return hits


def _search_entity(query: str, n: int) -> list[dict]:
    if not _entity_index:
        return []
    query_entities = _extract_entities(query)
    if not query_entities:
        return []

    chunk_score: dict[str, int] = {}

    # Single-entity hits
    for entity in query_entities:
        for cid in _entity_index.get(entity, []):
            chunk_score[cid] = chunk_score.get(cid, 0) + 1

    # Entity pair hits — multi-hop: "dashpass + refund" in same chunk scores higher
    sorted_q_entities = sorted(set(query_entities))
    for i in range(len(sorted_q_entities)):
        for j in range(i + 1, len(sorted_q_entities)):
            pair_key = f"{sorted_q_entities[i]}+{sorted_q_entities[j]}"
            for cid in _entity_pair_index.get(pair_key, []):
                chunk_score[cid] = chunk_score.get(cid, 0) + 2   # pair match worth 2×

    # Build a fast id→entry lookup to avoid O(n²) scan
    corpus_map = {e["id"]: e for e in _bm25_corpus}

    top_ids = sorted(chunk_score, key=lambda x: chunk_score[x], reverse=True)[:n]
    hits = []
    for cid in top_ids:
        entry = corpus_map.get(cid)
        if entry:
            hits.append({
                "chunk_id": cid,
                "content": entry["text"],
                "metadata": entry["metadata"],
                "source": entry["metadata"].get("filename", "KB"),
                "entity_score": chunk_score[cid],
                "via_entity": True,
            })
    return hits


# ── Call transcript indexing ──────────────────────────────────────────────────

async def search_calls(query: str, customer_id: str, n_results: int = 2) -> list[dict]:
    if _calls_collection is None:
        return []
    embedding = await embed_single(query)
    try:
        count = _calls_collection.count()
        if count == 0:
            return []
        results = _calls_collection.query(
            query_embeddings=[embedding],
            n_results=min(n_results, count),
            where={"customer_id": customer_id},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning(f"Calls query failed: {exc}")
        return []

    hits = []
    for doc, meta, dist in zip(
        results.get("documents", [[]])[0],
        results.get("metadatas", [[]])[0],
        results.get("distances", [[]])[0],
    ):
        if dist < CALL_DISTANCE_THRESHOLD:
            hits.append({
                "content": doc,
                "source": f"Past call {meta.get('call_id', '')[:8]}",
                "relevance": round(1 - dist, 3),
                "call_id": meta.get("call_id", ""),
            })
    return hits


async def index_call_transcript(call_id: str, customer_id: str, transcript_lines: list[dict]) -> None:
    if _calls_collection is None:
        return
    full_text = "\n".join(
        f"[{line.get('speaker','')}]: {line.get('content', line.get('text',''))}"
        for line in transcript_lines
        if line.get("content") or line.get("text")
    )
    if not full_text.strip():
        return

    from knowledge.document_parser import chunk_text
    chunks = chunk_text(full_text)
    if not chunks:
        return

    embeddings = await embed_texts(chunks)
    ids = [f"{call_id}__chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"call_id": call_id, "customer_id": customer_id, "chunk_index": i, "type": "call"}
                 for i in range(len(chunks))]
    _calls_collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    logger.info(f"Indexed {len(chunks)} transcript chunks for call {call_id}")


# ── Inspector functions ───────────────────────────────────────────────────────

def get_doc_chunks(doc_id: str) -> list[dict]:
    """Return all chunks for a document, sorted by chunk_index."""
    if _kb_collection is None:
        return []
    try:
        all_cols = list(_collections.values()) if _collections else [_kb_collection]
        all_docs, all_metas = [], []
        for col in all_cols:
            results = col.get(
                where={"doc_id": doc_id},
                include=["documents", "metadatas"],
            )
            all_docs.extend(results.get("documents", []))
            all_metas.extend(results.get("metadatas", []))
        pairs = list(zip(all_docs, all_metas))
        pairs.sort(key=lambda x: x[1].get("chunk_index", 0))
        return [
            {
                "index": meta.get("chunk_index", i),
                "content": doc,
                "tokens": len(TOKENIZER.encode(doc)),
                "category": meta.get("category", "general"),
            }
            for i, (doc, meta) in enumerate(pairs)
        ]
    except Exception as e:
        logger.warning(f"get_doc_chunks failed: {e}")
        return []


def get_chunk_similarity(doc_id: str) -> dict:
    """Return N×N cosine similarity matrix for all chunks of a document."""
    if _kb_collection is None:
        return {"chunks": [], "matrix": []}
    try:
        all_cols = list(_collections.values()) if _collections else [_kb_collection]
        embeddings_all, docs_all, metas_all = [], [], []
        for col in all_cols:
            results = col.get(
                where={"doc_id": doc_id},
                include=["embeddings", "documents", "metadatas"],
            )
            emb = results.get("embeddings")
            if emb is not None:
                embeddings_all.extend(emb)
            docs_all.extend(results.get("documents") or [])
            metas_all.extend(results.get("metadatas") or [])

        embeddings, docs, metas = embeddings_all, docs_all, metas_all

        if len(embeddings) < 2:
            return {"chunks": [], "matrix": []}

        # Sort by chunk_index
        combined = sorted(zip(embeddings, docs, metas), key=lambda x: x[2].get("chunk_index", 0))
        embeddings, docs, _ = zip(*combined)

        E = np.array(embeddings)
        norms = np.linalg.norm(E, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-8, norms)   # avoid div-by-zero
        E_norm = E / norms
        sim_matrix = (E_norm @ E_norm.T).tolist()

        previews = [
            {"index": i, "preview": doc[:80]}
            for i, doc in enumerate(docs)
        ]
        return {"chunks": previews, "matrix": sim_matrix}
    except Exception as e:
        logger.warning(f"get_chunk_similarity failed: {e}")
        return {"chunks": [], "matrix": []}


def get_suggested_questions(doc_id: str) -> list[str]:
    """Return headings extracted at ingest time for the given document."""
    return _doc_headings.get(doc_id, [])


# ── List documents ────────────────────────────────────────────────────────────

def list_documents() -> list[dict]:
    if _kb_collection is None:
        return []
    try:
        results = _kb_collection.get(include=["metadatas"])
        metas = results.get("metadatas", [])
        seen: dict[str, dict] = {}
        for meta in metas:
            doc_id = meta.get("doc_id", "")
            if doc_id and doc_id not in seen:
                seen[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename", ""),
                    "file_type": meta.get("file_type", ""),
                    "category": meta.get("category", "general"),
                }
        return list(seen.values())
    except Exception as exc:
        logger.warning(f"list_documents failed: {exc}")
        return []


def get_chunk_count(doc_id: str) -> int:
    if _kb_collection is None:
        return 0
    try:
        all_cols = list(_collections.values()) if _collections else [_kb_collection]
        total = 0
        for col in all_cols:
            results = col.get(where={"doc_id": doc_id})
            total += len(results.get("ids", []))
        return total
    except Exception:
        return 0
