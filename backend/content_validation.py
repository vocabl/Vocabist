"""Content validation (Phase B).

Deterministic, DB-free validation of a canonical vocabulary record. Pure Python
so it is trivially testable and reusable by ingestion, future admin tools, AI
content pipelines, quality reports, and a future PostgreSQL migration.

A ``ValidationResult`` separates hard ``errors`` (block publication) from
``warnings`` (quality issues that may still allow REVIEW status) and carries the
``normalized_data`` that ingestion should persist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from vocab_schema import (
    normalize_headword,
    canonical_id,
    to_canonical_storage,
    WORD_RELATION_FIELDS,
)

# ---- controlled vocabularies -------------------------------------------------
CEFR_VALUES: Set[str] = {"A1", "A2", "B1", "B2", "C1", "C2"}

CONTENT_STATUSES: List[str] = ["DRAFT", "REVIEW", "PUBLISHED", "ARCHIVED"]
CONTENT_STATUS_SET: Set[str] = set(CONTENT_STATUSES)

PROVENANCES: List[str] = ["CURATED", "AI_GENERATED", "IMPORTED", "ADMIN_CREATED"]
PROVENANCE_SET: Set[str] = set(PROVENANCES)

# Map historical (lowercase) provenance values → standardized representation.
LEGACY_PROVENANCE_MAP: Dict[str, str] = {
    "seed": "CURATED",
    "curated": "CURATED",
    "ai_generated": "AI_GENERATED",
    "imported": "IMPORTED",
    "admin_created": "ADMIN_CREATED",
}


def standardize_provenance(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip()
    if v in PROVENANCE_SET:
        return v
    return LEGACY_PROVENANCE_MAP.get(v.lower())


@dataclass
class ValidationResult:
    valid: bool = True
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)
    normalized_data: Optional[Dict[str, Any]] = None

    def error(self, code: str, fld: str, message: str) -> None:
        self.errors.append({"code": code, "field": fld, "message": message})
        self.valid = False

    def warn(self, code: str, fld: str, message: str) -> None:
        self.warnings.append({"code": code, "field": fld, "message": message})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "normalized_data": self.normalized_data,
        }


def _relation_headword(entry: Any) -> Optional[str]:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("headword")
    return None


def validate_word(
    raw: Dict[str, Any],
    *,
    id_by_key: Optional[Dict[str, str]] = None,
    known_word_ids: Optional[Set[str]] = None,
    known_exam_slugs: Optional[Set[str]] = None,
    existing_id: Optional[str] = None,
) -> ValidationResult:
    """Validate one vocabulary record.

    ``id_by_key`` maps canonical_key → canonical id (used for duplicate
    detection and to resolve relationship refs). ``known_exam_slugs`` enables
    exam-reference verification; when ``None`` exam refs are reported as
    unverifiable warnings rather than errors (never invents exam records).
    """
    res = ValidationResult()
    id_by_key = id_by_key or {}
    known_word_ids = known_word_ids if known_word_ids is not None else set(id_by_key.values())

    # ---- IDENTITY ----
    headword = raw.get("headword")
    ckey = normalize_headword(headword)
    if not headword or not str(headword).strip():
        res.error("MISSING_HEADWORD", "headword", "headword is required")
    if not ckey:
        res.error("MISSING_CANONICAL_KEY", "canonical_key", "canonical_key could not be derived")
    else:
        # if a canonical_key was supplied it must already be normalized
        supplied = raw.get("canonical_key")
        if supplied is not None and supplied != ckey:
            res.error("CANONICAL_KEY_NOT_NORMALIZED", "canonical_key",
                      f"canonical_key '{supplied}' is not normalized (expected '{ckey}')")
        owner = id_by_key.get(ckey)
        if owner and owner != existing_id:
            res.error("DUPLICATE_CANONICAL_KEY", "canonical_key",
                      f"canonical_key '{ckey}' already belongs to '{owner}'")

    # ---- DEFINITIONS ----
    meanings = raw.get("meanings")
    has_meaning_def = False
    if meanings is not None:
        if not isinstance(meanings, list) or any(not isinstance(m, dict) for m in meanings):
            res.error("MALFORMED_MEANINGS", "meanings", "meanings must be a list of objects")
        else:
            has_meaning_def = any((m.get("definition") or "").strip() for m in meanings)
    simple = (raw.get("simple_definition") or "").strip()
    if not simple and not has_meaning_def:
        res.error("MISSING_DEFINITION", "simple_definition",
                  "at least one usable definition (simple_definition or a meaning) is required")
    if not (raw.get("easy_meaning") or "").strip() and not simple:
        res.warn("MISSING_EASY_DEFINITION", "easy_meaning", "no easy/simple definition supplied")

    # ---- CEFR ----
    cefr = raw.get("cefr")
    if cefr in (None, ""):
        res.warn("MISSING_CEFR", "cefr", "CEFR level is missing")
    elif cefr not in CEFR_VALUES:
        res.error("INVALID_CEFR", "cefr", f"invalid CEFR '{cefr}' (allowed: {sorted(CEFR_VALUES)})")

    # ---- PRONUNCIATION (structure only, when supplied) ----
    pron = raw.get("pronunciation")
    if pron is not None:
        ok = isinstance(pron, dict)
        if ok:
            for accent in ("us", "uk"):
                a = pron.get(accent)
                if a is None:
                    continue
                if not isinstance(a, dict) or (a.get("ipa") is not None and not isinstance(a.get("ipa"), str)) \
                        or (a.get("audio") is not None and not isinstance(a.get("audio"), str)):
                    ok = False
                    break
        if not ok:
            res.error("MALFORMED_PRONUNCIATION", "pronunciation",
                      "pronunciation must be {us:{ipa,audio}, uk:{ipa,audio}}")

    # ---- RELATIONSHIPS ----
    for fld in WORD_RELATION_FIELDS:
        entries = raw.get("relations", {}).get(fld) if isinstance(raw.get("relations"), dict) else raw.get(fld)
        if entries is None:
            continue
        if not isinstance(entries, list):
            res.error("MALFORMED_RELATION", fld, f"{fld} must be a list")
            continue
        seen: Set[str] = set()
        for entry in entries:
            hw = _relation_headword(entry)
            if hw is None or not str(hw).strip():
                res.error("MALFORMED_RELATION", fld, f"{fld} entry has no headword: {entry!r}")
                continue
            rkey = normalize_headword(hw)
            if rkey == ckey and ckey:
                res.error("SELF_REFERENCE", fld, f"{fld} references the word itself ('{hw}')")
            if rkey in seen:
                res.warn("DUPLICATE_RELATION", fld, f"{fld} lists '{hw}' more than once")
            seen.add(rkey)
            if isinstance(entry, dict) and entry.get("ref") and entry["ref"] not in known_word_ids:
                res.warn("BROKEN_RELATION_REF", fld,
                         f"{fld} ref '{entry['ref']}' does not resolve to a known word")

    # ---- EXAM REFERENCES ----
    exam_refs = raw.get("exam_relevance") or []
    if not isinstance(exam_refs, list):
        res.error("MALFORMED_EXAM_RELEVANCE", "exam_relevance", "exam_relevance must be a list")
    else:
        for slug in exam_refs:
            if known_exam_slugs is None:
                res.warn("UNVERIFIABLE_EXAM_REF", "exam_relevance",
                         f"cannot verify exam '{slug}' (no exam list supplied)")
            elif slug not in known_exam_slugs:
                res.error("INVALID_EXAM_REF", "exam_relevance", f"exam '{slug}' does not exist")

    # ---- METADATA ----
    status = raw.get("status")
    if status is not None and status not in CONTENT_STATUS_SET:
        res.error("INVALID_STATUS", "status", f"invalid status '{status}' (allowed: {CONTENT_STATUSES})")
    prov = raw.get("provenance")
    if prov is not None and standardize_provenance(prov) is None:
        res.error("INVALID_PROVENANCE", "provenance", f"invalid provenance '{prov}' (allowed: {PROVENANCES})")
    for numeric in ("frequency", "academic_importance"):
        val = raw.get(numeric)
        if val is not None and (not isinstance(val, (int, float)) or val < 0 or val > 10):
            res.warn("INVALID_METADATA", numeric, f"{numeric} should be a number in 0..10 (got {val!r})")
    if not (raw.get("topic") or "").strip():
        res.warn("MISSING_TOPIC", "topic", "topic is missing")

    # ---- NORMALIZED DATA (best effort, even if invalid, for reporting) ----
    if ckey:
        merged = dict(raw)
        merged["headword"] = ckey
        merged.update(to_canonical_storage(merged, id_by_key))
        if merged.get("provenance"):
            merged["provenance"] = standardize_provenance(merged["provenance"]) or merged["provenance"]
        res.normalized_data = merged
    return res


def canonical_id_for(headword: str) -> str:
    """Public helper so ingestion and tests share one id derivation."""
    return canonical_id(headword)
