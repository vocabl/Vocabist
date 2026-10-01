"""Content ingestion pipeline (Phase B/C) — repository-backed.

Preserves original ingest logic exactly.  Only direct ``db.*`` calls have been
replaced with DatabaseRepository method calls.  All business rules, validation
flow, provenance handling, and lifecycle migration are unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from vocab_schema import normalize_headword, canonical_id, to_canonical_storage
from content_validation import (
    validate_word,
    standardize_provenance,
    CONTENT_STATUS_SET,
)
from graph_service import refresh_refs_for_new_key, relationship_quality_metrics


def _now():
    return datetime.now(timezone.utc)


def resolve_status(provenance: str, result, requested_status: Optional[str]) -> str:
    """Decide the content status for a *new* record.

    - AI_GENERATED never auto-publishes → REVIEW.
    - IMPORTED (dictionary-backed) stays PUBLISHED to preserve existing behavior.
    - CURATED / ADMIN_CREATED honor requested_status, but warnings downgrade
      PUBLISHED → REVIEW.
    """
    prov = provenance
    if prov == "AI_GENERATED":
        return "REVIEW"
    if prov == "IMPORTED":
        return "PUBLISHED"
    req = requested_status or "PUBLISHED"
    if req not in CONTENT_STATUS_SET:
        req = "DRAFT"
    if req == "PUBLISHED" and result.warnings:
        return "REVIEW"
    return req


async def _load_context(repo) -> Dict[str, Any]:
    """Build the shared context (id_by_key map + known exam slugs)."""
    words = await repo.load_all_words_minimal()
    id_by_key: Dict[str, str] = {}
    for w in words:
        k = normalize_headword(w.get("headword", ""))
        if k and k not in id_by_key:
            id_by_key[k] = w["id"]
    exam_slugs = await repo.get_exam_slugs()
    return {
        "id_by_key": id_by_key,
        "known_word_ids": set(id_by_key.values()),
        "exam_slugs": exam_slugs,
    }


async def ingest_word(
    repo,
    raw: Dict[str, Any],
    *,
    provenance: str,
    requested_status: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest a single record. Returns a structured outcome; never raises for
    validation problems.

    outcome = {action, id, status, validation}
      action ∈ {"exists", "created", "rejected"}
    """
    prov = standardize_provenance(provenance) or "IMPORTED"
    ckey = normalize_headword(raw.get("headword"))
    if not ckey:
        res = validate_word(raw)  # will contain MISSING_HEADWORD
        return {"action": "rejected", "id": None, "status": None, "validation": res.to_dict()}

    own_context = context is None
    if own_context:
        context = await _load_context(repo)

    # 1) dedupe by canonical_key — return existing, never overwrite trusted content
    existing_id = context["id_by_key"].get(ckey)
    if existing_id:
        return {"action": "exists", "id": existing_id, "status": None, "validation": None}

    # 2) validate against known refs/exams
    res = validate_word(
        raw,
        id_by_key=context["id_by_key"],
        known_word_ids=context["known_word_ids"],
        known_exam_slugs=context["exam_slugs"],
    )
    if not res.valid:
        return {"action": "rejected", "id": None, "status": None, "validation": res.to_dict()}

    # 3) build canonical doc and assign status
    wid = canonical_id(raw.get("headword"))
    status = resolve_status(prov, res, requested_status)
    doc = dict(res.normalized_data or {})
    doc.update({
        "id": wid,
        "headword": ckey,
        "canonical_key": ckey,
        "provenance": prov,
        "status": status,
        "lifecycle_version": 1,
        "created_at": _now(),
    })
    await repo.upsert_word(wid, doc)

    # keep shared context consistent for deterministic bulk runs
    context["id_by_key"][ckey] = wid
    context["known_word_ids"].add(wid)

    # targeted re-resolution: fill previously-unresolved refs now pointing here
    await refresh_refs_for_new_key(repo, ckey, wid)
    return {"action": "created", "id": wid, "status": status, "validation": res.to_dict()}


async def bulk_ingest(
    repo,
    records: List[Dict[str, Any]],
    *,
    provenance: str,
    requested_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest many records deterministically and idempotently.

    Each record is independent — one bad record never corrupts the rest.
    Safe to re-run: already-present records report ``exists``.
    """
    context = await _load_context(repo)
    results: List[Dict[str, Any]] = []
    counts = {"created": 0, "exists": 0, "rejected": 0}
    for i, rec in enumerate(records):
        outcome = await ingest_word(repo, rec, provenance=provenance,
                                    requested_status=requested_status, context=context)
        counts[outcome["action"]] = counts.get(outcome["action"], 0) + 1
        results.append({"index": i, "headword": rec.get("headword"), **outcome})
    return {"total": len(records), **counts, "results": results}


async def quality_report(repo) -> Dict[str, Any]:
    """Read-only validation pass over the whole bank. Never modifies records."""
    context = await _load_context(repo)
    words = await repo.load_all_words_full()

    key_owners: Dict[str, List[str]] = {}
    for w in words:
        key_owners.setdefault(normalize_headword(w.get("headword", "")), []).append(w["id"])
    duplicate_canonical_keys = {k: v for k, v in key_owners.items() if len(v) > 1}

    issues_by_code: Dict[str, int] = {}
    invalid: List[Dict[str, Any]] = []
    missing_provenance: List[str] = []
    invalid_status: List[str] = []
    for w in words:
        if not w.get("provenance"):
            missing_provenance.append(w["id"])
        if w.get("status") not in CONTENT_STATUS_SET:
            invalid_status.append(w["id"])
        res = validate_word(
            w,
            id_by_key=context["id_by_key"],
            known_word_ids=context["known_word_ids"],
            known_exam_slugs=context["exam_slugs"],
            existing_id=w["id"],
        )
        for item in res.errors:
            issues_by_code[item["code"]] = issues_by_code.get(item["code"], 0) + 1
        for item in res.warnings:
            issues_by_code[item["code"]] = issues_by_code.get(item["code"], 0) + 1
        if not res.valid:
            invalid.append({"id": w["id"], "headword": w.get("headword"), "errors": res.errors})

    return {
        "total_words": len(words),
        "invalid_count": len(invalid),
        "duplicate_canonical_keys": duplicate_canonical_keys,
        "missing_provenance": missing_provenance,
        "invalid_status": invalid_status,
        "issues_by_code": issues_by_code,
        "invalid_samples": invalid[:50],
        "relationships": await relationship_quality_metrics(repo),
    }


async def migrate_content_lifecycle(repo) -> int:
    """Idempotently standardize provenance + ensure lifecycle_version on every
    existing word, without ever downgrading live PUBLISHED content.

    Previously accepted a Motor ``db`` arg; now accepts a DatabaseRepository.
    """
    pending = await repo.find_words_needing_lifecycle()
    migrated = 0
    for w in pending:
        update: Dict[str, Any] = {"lifecycle_version": 1}
        std = standardize_provenance(w.get("provenance"))
        if std and std != w.get("provenance"):
            update["provenance"] = std
            if not w.get("provenance_original"):
                update["provenance_original"] = w.get("provenance")
        elif not w.get("provenance"):
            update["provenance"] = "CURATED"
        status = w.get("status")
        if status not in CONTENT_STATUS_SET:
            update["status"] = "PUBLISHED"
        await repo.update_word(w["id"], update)
        migrated += 1
    return migrated
