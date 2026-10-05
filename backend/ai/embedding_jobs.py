"""Embedding generation jobs — background job system for batch embedding creation.

Uses the existing job architecture pattern from ai/jobs.py.
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .tasks.semantic_search import generate_embeddings_for_words
from .errors import AIError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_embedding_job(
    repo,
    *,
    mode: str = "missing",  # missing | stale | all | selected
    word_ids: Optional[List[str]] = None,
    model: str = "nemotron-embed",
    version: str = "v1",
    admin_id: str,
) -> Dict[str, Any]:
    """Create and start a background embedding generation job."""
    job_id = "emb_" + uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "task": "embedding_generation",
        "status": "QUEUED",
        "mode": mode,
        "embedding_model": model,
        "embedding_version": version,
        "total_words": 0,
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "admin_id": admin_id,
        "error": None,
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
    }

    # Save to Supabase if available, otherwise use file store
    try:
        await repo.create_embedding_job(job)
    except Exception:
        from . import state_store
        await state_store.save_job(job)

    asyncio.create_task(_run_embedding_job(repo, job_id, mode, word_ids, model, version, admin_id))
    return job


async def _run_embedding_job(
    repo,
    job_id: str,
    mode: str,
    word_ids: Optional[List[str]],
    model: str,
    version: str,
    admin_id: str,
) -> None:
    """Background task that generates embeddings for vocabulary words."""
    import time
    start_time = time.monotonic()

    async def update_job(patch):
        try:
            await repo.update_embedding_job(job_id, patch)
        except Exception:
            from . import state_store
            await state_store.update_job(job_id, patch)

    await update_job({"status": "RUNNING", "started_at": _now_iso()})

    try:
        # Get words to embed based on mode
        if mode == "selected" and word_ids:
            words = await repo.find_words_by_ids(word_ids)
        elif mode == "all":
            words = await repo.find_published_words()
        elif mode == "stale":
            words = await _get_stale_words(repo, model, version)
        else:  # missing
            words = await _get_words_missing_embeddings(repo, model, version)

        total = len(words)
        await update_job({"total_words": total})

        if total == 0:
            await update_job({
                "status": "COMPLETED",
                "completed_at": _now_iso(),
                "duration_ms": int((time.monotonic() - start_time) * 1000),
            })
            return

        # Process in batches
        batch_size = 20
        processed = successful = failed = skipped = 0

        for i in range(0, total, batch_size):
            batch = words[i:i + batch_size]
            result = await generate_embeddings_for_words(
                repo, batch,
                model=model, version=version,
                admin_id=admin_id, batch_size=batch_size,
            )
            processed += result["processed"]
            successful += result["successful"]
            failed += result["failed"]
            skipped += result["skipped"]

            await update_job({
                "processed": processed,
                "successful": successful,
                "failed": failed,
                "skipped": skipped,
            })

        duration = int((time.monotonic() - start_time) * 1000)
        status = "COMPLETED" if failed == 0 else ("PARTIAL" if successful > 0 else "FAILED")
        await update_job({
            "status": status,
            "completed_at": _now_iso(),
            "duration_ms": duration,
            "processed": processed,
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
        })

    except Exception as e:
        duration = int((time.monotonic() - start_time) * 1000)
        await update_job({
            "status": "FAILED",
            "completed_at": _now_iso(),
            "duration_ms": duration,
            "error": f"{type(e).__name__}: {e}",
        })


async def _get_words_missing_embeddings(repo, model: str, version: str) -> List[Dict[str, Any]]:
    """Get published words that don't have embeddings yet."""
    all_published = await repo.find_published_words()
    embedded_ids = await repo.get_embedded_word_ids(model, version)
    return [w for w in all_published if w["id"] not in embedded_ids]


async def _get_stale_words(repo, model: str, version: str) -> List[Dict[str, Any]]:
    """Get words whose embedding content_hash doesn't match current content."""
    from .tasks.semantic_search import build_embedding_text, content_hash
    all_published = await repo.find_published_words()
    embeddings = await repo.get_all_embedding_hashes(model, version)
    hash_map = {e["word_id"]: e.get("content_hash", "") for e in embeddings}

    stale = []
    for w in all_published:
        current_hash = content_hash(build_embedding_text(w))
        stored_hash = hash_map.get(w["id"], "")
        if stored_hash and stored_hash != current_hash:
            stale.append(w)
    return stale
