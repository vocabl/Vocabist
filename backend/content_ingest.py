"""Content ingestion (Phase B).

Controlled path for creating/updating canonical vocabulary. Thin DB coupling on
top of the pure ``content_validation`` + ``vocab_schema`` modules so the same
logic is reusable by ``/api/words/import``, bulk imports, future admin tools,
AI content pipelines, and migration scripts.

Guarantees:
- normalize → canonical_key → detect existing → validate → persist only when
  permitted;
- never silently creates duplicates (dedupe by canonical_key);
- never overwrites an existing trusted record;
- AI-generated content never auto-publishes (enters REVIEW) and must pass
  structural validation before storage;
- idempotent and safe to re-run.
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


def _now():
    return datetime.now(timezone.utc)


def resolve_status(provenance: str, result, requested_status: Optional[str]) -> str:
    """Decide the content status for a *new* record.

    - AI_GENERATED never auto-publishes → REVIEW.
    - IMPORTED (dictionary-backed) stays PUBLISHED to preserve existing
      /api/words/import behavior (only reached when structurally valid).
    - CURATED / ADMIN_CREATED honor the requested status, but any warnings
      downgrade a PUBLISHED request to REVIEW (errors already blocked storage).
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


async def _load_context(db) -> Dict[str, Any]:
    words = await db.words.find({}, {"_id": 0, "id": 1, "headword": 1}).to_list(200000)
    id_by_key: Dict[str, str] = {}
    for w in words:
        k = normalize_headword(w.get("headword", ""))
        if k and k not in id_by_key:
            id_by_key[k] = w["id"]
    exam_slugs = {e["slug"] for e in await db.exams.find({}, {"_id": 0, "slug": 1}).to_list(1000)}
    return {"id_by_key": id_by_key, "known_word_ids": set(id_by_key.values()), "exam_slugs": exam_slugs}


async def ingest_word(
    db,
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
        context = await _load_context(db)

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
    await db.words.update_one({"id": wid}, {"$set": doc}, upsert=True)

    # keep shared context consistent for deterministic bulk runs
    context["id_by_key"][ckey] = wid
    context["known_word_ids"].add(wid)
    return {"action": "created", "id": wid, "status": status, "validation": res.to_dict()}


async def bulk_ingest(
    db,
    records: List[Dict[str, Any]],
    *,
    provenance: str,
    requested_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest many records deterministically and idempotently.

    Each record is independent — one bad record never corrupts the rest. Safe to
    re-run: already-present records report ``exists``.
    """
    context = await _load_context(db)
    results: List[Dict[str, Any]] = []
    counts = {"created": 0, "exists": 0, "rejected": 0}
    for i, rec in enumerate(records):
        outcome = await ingest_word(db, rec, provenance=provenance,
                                    requested_status=requested_status, context=context)
        counts[outcome["action"]] = counts.get(outcome["action"], 0) + 1
        results.append({"index": i, "headword": rec.get("headword"), **outcome})
    return {"total": len(records), **counts, "results": results}


async def quality_report(db) -> Dict[str, Any]:
    """Read-only validation pass over the whole bank. Never modifies records."""
    context = await _load_context(db)
    words = await db.words.find({}, {"_id": 0}).to_list(200000)

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
    }


async def migrate_content_lifecycle(db) -> int:
    """Idempotently standardize provenance + ensure a lifecycle status on every
    existing word, without ever downgrading working (PUBLISHED) content.

    Existing records keep their status (all currently PUBLISHED), so the live
    app is unaffected. Historical provenance is preserved under
    ``provenance_original`` when it is rewritten to the standardized value.
    """
    pending = await db.words.find({"lifecycle_version": {"$ne": 1}}, {"_id": 0}).to_list(200000)
    migrated = 0
    for w in pending:
        update: Dict[str, Any] = {"lifecycle_version": 1}
        std = standardize_provenance(w.get("provenance"))
        if std and std != w.get("provenance"):
            update["provenance"] = std
            if not w.get("provenance_original"):
                update["provenance_original"] = w.get("provenance")
        elif not w.get("provenance"):
            update["provenance"] = "CURATED"  # grandfather untagged legacy content
        status = w.get("status")
        if status not in CONTENT_STATUS_SET:
            update["status"] = "PUBLISHED"  # grandfather existing working content
        await db.words.update_one({"id": w["id"]}, {"$set": update})
        migrated += 1
    return migrated
