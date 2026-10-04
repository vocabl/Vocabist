"""Asynchronous AI vocabulary generation jobs.

Simplest reliable architecture compatible with the single-process FastAPI
runtime: jobs are persisted as JSON files (state_store) and executed via
asyncio background tasks. No Redis/Celery/Kafka.

Generated words ALWAYS flow through the existing Vocabist content pipeline
(content_ingest.bulk_ingest, provenance=AI_GENERATED) and land in REVIEW — they
are never auto-published.
"""
from __future__ import annotations

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schemas import JobStatus
from .tasks import vocabulary
from .errors import AIError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_generation_job(repo, params: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
    from . import state_store
    job = {
        "id": "job_" + uuid.uuid4().hex[:12],
        "task": "vocabulary_generation",
        "status": JobStatus.QUEUED,
        "params": params,
        "requested_count": int(params.get("count", 10)),
        "generated_count": 0,
        "valid_count": 0,
        "invalid_count": 0,
        "duplicate_count": 0,
        "model": None,
        "provider": None,
        "fallback_used": False,
        "word_ids": [],
        "error": None,
        "admin_id": admin_id,
        "created_at": _now_iso(),
        "started_at": None,
        "completed_at": None,
        "log": [],
    }
    await state_store.save_job(job)
    # fire-and-forget background execution
    asyncio.create_task(_run_job(repo, job["id"]))
    return job


async def _run_job(repo, job_id: str) -> None:
    from . import state_store
    from content_ingest import bulk_ingest

    job = await state_store.get_job(job_id)
    if not job or job.get("status") == JobStatus.CANCELLED:
        return
    params = job["params"]
    requested = job["requested_count"]
    await state_store.update_job(job_id, {"status": JobStatus.RUNNING, "started_at": _now_iso()})

    try:
        # existing headwords to steer the model away from duplicates
        existing = await repo.load_all_words_minimal()
        avoid = [w.get("headword", "") for w in existing if w.get("headword")]

        created_ids: List[str] = []
        generated = valid = invalid = dup = 0
        model_key = provider = None
        fallback_used = False
        log: List[str] = []

        batch_size = min(25, max(1, requested))
        max_batches = 8
        batch = 0
        while valid < requested and batch < max_batches:
            # refresh cancellation state
            cur = await state_store.get_job(job_id)
            if cur and cur.get("status") == JobStatus.CANCELLED:
                return
            batch += 1
            need = min(batch_size, requested - valid + 3)  # slight over-ask to absorb dupes/rejects
            try:
                gen = await vocabulary.generate(
                    need,
                    cefr=params.get("cefr"),
                    topic=params.get("topic"),
                    part_of_speech=params.get("part_of_speech"),
                    exam=params.get("exam"),
                    vocabulary_type=params.get("vocabulary_type"),
                    enrichment_level=params.get("enrichment_level", "standard"),
                    avoid=avoid,
                    prefer_model=params.get("model"),
                    admin_id=job.get("admin_id"),
                    job_id=job_id,
                )
            except AIError as e:
                log.append(f"batch {batch}: generation failed ({e.code})")
                break

            model_key = gen.get("model_key") or model_key
            provider = gen.get("provider") or provider
            fallback_used = fallback_used or bool(gen.get("fallback_used"))
            entries = gen.get("entries", [])
            generated += len(entries)
            if not entries:
                log.append(f"batch {batch}: no usable entries")
                continue

            result = await bulk_ingest(repo, entries, provenance="AI_GENERATED")
            valid += result.get("created", 0)
            dup += result.get("exists", 0)
            invalid += result.get("rejected", 0)
            for item in result.get("results", []):
                if item.get("action") == "created" and item.get("id"):
                    created_ids.append(item["id"])
                    avoid.append(item.get("headword", ""))
            log.append(
                f"batch {batch}: +{result.get('created',0)} new, "
                f"{result.get('exists',0)} dup, {result.get('rejected',0)} rejected"
            )
            await state_store.update_job(job_id, {
                "generated_count": generated, "valid_count": valid,
                "invalid_count": invalid, "duplicate_count": dup,
                "word_ids": created_ids, "model": model_key, "provider": provider,
                "fallback_used": fallback_used, "log": log[-20:],
            })

        if valid == 0:
            status = JobStatus.FAILED
        elif valid < requested:
            status = JobStatus.PARTIAL
        else:
            status = JobStatus.COMPLETED

        await state_store.update_job(job_id, {
            "status": status, "completed_at": _now_iso(),
            "generated_count": generated, "valid_count": valid,
            "invalid_count": invalid, "duplicate_count": dup,
            "word_ids": created_ids, "model": model_key, "provider": provider,
            "fallback_used": fallback_used, "log": log[-20:],
        })
    except Exception as e:  # noqa: BLE001
        await state_store.update_job(job_id, {
            "status": JobStatus.FAILED, "completed_at": _now_iso(),
            "error": f"{type(e).__name__}: {e}",
        })


async def cancel_job(job_id: str) -> Optional[Dict[str, Any]]:
    from . import state_store
    job = await state_store.get_job(job_id)
    if not job:
        return None
    if job.get("status") in (JobStatus.QUEUED, JobStatus.RUNNING):
        return await state_store.update_job(job_id, {
            "status": JobStatus.CANCELLED, "completed_at": _now_iso(),
        })
    return job
