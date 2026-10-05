"""Semantic search — hybrid exact + vector search via the AI Gateway.

Uses Nemotron Embed 1B through the gateway for query embeddings and
Supabase pgvector for similarity search. Falls back gracefully to
text-only search when embeddings are unavailable.
"""
from __future__ import annotations

import hashlib
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..gateway import gateway
from ..errors import AIError
from ..schemas import Task

# ------------------------------------------------------------------ #
# Embedding text construction
# ------------------------------------------------------------------ #

def build_embedding_text(word: Dict[str, Any]) -> str:
    """Build a rich passage string for embedding a vocabulary word.

    Combines headword, definitions, examples, synonyms, topics, etc.
    into a normalized text block suitable for passage embedding.
    """
    parts: List[str] = []
    hw = word.get("headword", "")
    parts.append(hw)

    sd = word.get("simple_definition", "")
    if sd:
        parts.append(f"Definition: {sd}")

    em = word.get("easy_meaning", "")
    if em and em != sd:
        parts.append(f"Meaning: {em}")

    pos = word.get("part_of_speech", "")
    if pos:
        parts.append(f"Part of speech: {pos}")

    ex = word.get("example", "")
    if ex:
        parts.append(f"Example: {ex}")

    cefr = word.get("cefr", "")
    if cefr:
        parts.append(f"Level: {cefr}")

    topic = word.get("topic", "")
    if topic:
        parts.append(f"Topic: {topic}")

    for field in ("synonyms", "antonyms", "related"):
        items = word.get(field) or []
        if isinstance(items, list) and items:
            strs = []
            for item in items:
                if isinstance(item, str):
                    strs.append(item)
                elif isinstance(item, dict) and item.get("headword"):
                    strs.append(item["headword"])
            if strs:
                parts.append(f"{field.title()}: {', '.join(strs)}")

    wf = word.get("word_family") or []
    if isinstance(wf, list) and wf:
        parts.append(f"Word family: {', '.join(str(w) for w in wf)}")

    exams = word.get("exam_relevance") or []
    if isinstance(exams, list) and exams:
        parts.append(f"Exams: {', '.join(str(e) for e in exams)}")

    return " | ".join(parts)


def content_hash(text: str) -> str:
    """SHA256 hash of embedding text for staleness detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ #
# Query embedding
# ------------------------------------------------------------------ #

async def embed_query(
    query: str,
    *,
    prefer_model: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Embed a search query using input_type=query."""
    res = await gateway.run_embedding(
        [query], input_type="query",
        prefer_model=prefer_model, user_id=user_id,
    )
    vectors = res.data or []
    return {
        "vector": vectors[0] if vectors else [],
        "dimensions": len(vectors[0]) if vectors else 0,
        "model_key": res.model_key,
        "provider": res.provider,
    }


# ------------------------------------------------------------------ #
# Passage embedding (batch)
# ------------------------------------------------------------------ #

async def embed_passages(
    passages: List[str],
    *,
    prefer_model: Optional[str] = None,
    admin_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Embed multiple passages using input_type=passage."""
    res = await gateway.run_embedding(
        passages, input_type="passage",
        prefer_model=prefer_model, admin_id=admin_id,
    )
    vectors = res.data or []
    return {
        "vectors": vectors,
        "count": len(vectors),
        "dimensions": len(vectors[0]) if vectors else 0,
        "model_key": res.model_key,
        "provider": res.provider,
    }


# ------------------------------------------------------------------ #
# Embedding generation for a batch of words
# ------------------------------------------------------------------ #

async def generate_embeddings_for_words(
    repo,
    words: List[Dict[str, Any]],
    *,
    model: str = "nemotron-embed",
    version: str = "v1",
    admin_id: Optional[str] = None,
    batch_size: int = 20,
) -> Dict[str, Any]:
    """Generate and store embeddings for a list of words.

    Returns metrics: {processed, successful, failed, skipped}.
    """
    processed = successful = failed = skipped = 0

    for i in range(0, len(words), batch_size):
        batch = words[i:i + batch_size]
        texts = []
        word_ids = []
        hashes = []

        for w in batch:
            text = build_embedding_text(w)
            h = content_hash(text)
            # Check if embedding already exists with same hash
            existing = await repo.get_word_embedding(w["id"], model, version)
            if existing and existing.get("content_hash") == h:
                skipped += 1
                processed += 1
                continue
            texts.append(text)
            word_ids.append(w["id"])
            hashes.append(h)

        if not texts:
            continue

        try:
            result = await embed_passages(
                texts, prefer_model=model, admin_id=admin_id,
            )
            vectors = result.get("vectors", [])
            for j, (wid, vec, h) in enumerate(zip(word_ids, vectors, hashes)):
                if vec:
                    await repo.upsert_word_embedding(
                        wid, vec, model, version, h,
                    )
                    successful += 1
                else:
                    failed += 1
                processed += 1
        except AIError:
            failed += len(texts)
            processed += len(texts)

    return {
        "processed": processed,
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
    }


# ------------------------------------------------------------------ #
# Hybrid search
# ------------------------------------------------------------------ #

async def hybrid_search(
    repo,
    query: str,
    *,
    limit: int = 20,
    cefr: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Perform hybrid exact + semantic search.

    1. Always do exact/prefix text search (fast, no AI call)
    2. If query is long enough (>2 chars), attempt semantic search
    3. Merge and rank results
    """
    exact_results = []
    semantic_results = []
    search_types_used = ["exact"]

    # 1. Exact/text search — always runs
    try:
        total, words = await repo.list_words(query, None, cefr, None, 0, limit)
        exact_results = words
    except Exception:
        pass

    # 2. Semantic search — only for queries ≥ 3 chars
    semantic_available = False
    if len(query.strip()) >= 3:
        try:
            qr = await embed_query(query, user_id=user_id)
            vector = qr.get("vector")
            if vector and len(vector) > 0:
                sem_results = await repo.semantic_search(
                    vector,
                    threshold=0.3,
                    limit=limit,
                    cefr=cefr,
                )
                semantic_results = sem_results
                semantic_available = True
                if semantic_results:
                    search_types_used.append("semantic")
        except Exception:
            # Semantic search failed — exact search still works
            pass

    # 3. Merge results with ranking
    merged = _merge_results(exact_results, semantic_results, query, limit)

    return {
        "words": merged,
        "total": len(merged),
        "search_types": search_types_used,
        "semantic_available": semantic_available,
        "query": query,
    }


def _merge_results(
    exact: List[Dict[str, Any]],
    semantic: List[Dict[str, Any]],
    query: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Merge exact and semantic results with intelligent ranking.

    Priority: exact headword > prefix > text match > semantic similarity
    """
    q = query.lower().strip()
    seen_ids = set()
    result = []

    # Score exact results
    for w in exact:
        wid = w["id"]
        if wid in seen_ids:
            continue
        seen_ids.add(wid)
        hw = (w.get("headword") or "").lower()
        if hw == q:
            score = 1.0  # exact headword match
            match_type = "exact"
        elif hw.startswith(q):
            score = 0.9  # prefix match
            match_type = "prefix"
        else:
            score = 0.7  # text/definition match
            match_type = "text"
        result.append({**w, "_score": score, "_match_type": match_type})

    # Score semantic results
    for sw in semantic:
        wid = sw["word_id"] if "word_id" in sw else sw.get("id", "")
        if wid in seen_ids:
            # Boost existing result if semantic also matched
            for r in result:
                if r["id"] == wid and r.get("_match_type") != "exact":
                    r["_score"] = min(1.0, r["_score"] + 0.1)
                    r["_match_type"] = r["_match_type"] + "+semantic"
            continue
        seen_ids.add(wid)
        sim = sw.get("similarity", 0.5)
        # Scale semantic score: 0.3-1.0 similarity → 0.3-0.65 score
        score = 0.3 + (sim * 0.35)
        # We need to fetch full word data for semantic-only results
        result.append({
            **sw,
            "id": wid,
            "_score": score,
            "_match_type": "semantic",
            "_similarity": sim,
        })

    # Sort by score descending
    result.sort(key=lambda r: -r["_score"])

    # Clean internal fields for output
    output = []
    for r in result[:limit]:
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        clean["match_type"] = r.get("_match_type", "unknown")
        if r.get("_similarity") is not None:
            clean["similarity"] = round(r["_similarity"], 3)
        output.append(clean)

    return output
