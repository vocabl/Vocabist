"""Canonical vocabulary schema (Phase A).

One canonical identity per vocabulary item. This module is pure (no DB access)
so it stays trivially unit-testable and portable to a future PostgreSQL layer.

Design goals:
- ``id`` + ``canonical_key`` are the stable canonical identity of a word.
- Relationships resolve to canonical word references (``ref`` = canonical id)
  instead of unreliable plain strings, while still carrying the original
  ``headword`` string for display and for words not yet in the bank.
- The model can *hold* the full superset of vocabulary attributes (multiple
  meanings, US/UK pronunciation, translations, school relevance, etc.) without
  forcing every consumer to change. Legacy flat fields are preserved verbatim.

Storage stays practical for MongoDB (relations + meanings + pronunciation are
embedded on the word document). In PostgreSQL these embedded structures map
cleanly to ``word_meanings`` / ``word_pronunciation`` / ``word_relations`` tables
keyed by the same canonical ``id``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

# Content lifecycle + provenance vocabularies. Phase A only records/preserves
# these; full lifecycle enforcement/validation is Phase B.
CONTENT_STATUSES = ["DRAFT", "REVIEW", "PUBLISHED", "ARCHIVED"]
PROVENANCES = ["seed", "curated", "ai_generated", "imported", "admin_created"]

# Relationship fields whose entries are other canonical words → get canonical refs.
WORD_RELATION_FIELDS = ["synonyms", "antonyms", "related", "confusing_words"]
# Morphological fields are strings (roots/affixes/family members) that are NOT
# necessarily standalone canonical words → kept as plain strings.
MORPH_FIELDS = ["word_family", "roots", "prefixes", "suffixes"]

RELATION_FIELDS = WORD_RELATION_FIELDS + MORPH_FIELDS


def normalize_headword(text: Optional[str]) -> str:
    """Canonical key for a headword.

    Lowercase, trim, collapse internal whitespace, and drop characters other
    than letters/digits/space/apostrophe/hyphen. Two spellings that differ only
    by case, spacing or stray punctuation collapse to the same key, which is
    what the unique index uses to prevent duplicate canonical words.
    """
    if not text:
        return ""
    t = str(text).lower().strip()
    t = re.sub(r"[^a-z0-9 '\-]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def canonical_id(headword: Optional[str]) -> str:
    """Deterministic canonical word id for a *new* word.

    Existing words keep their stored ``id``; this is only used when creating new
    canonical words (import/admin) so the id is stable and slug-like.
    """
    key = normalize_headword(headword)
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


def _as_headword(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("headword") or ""
    return ""


def build_relations(doc: Dict[str, Any], id_by_key: Dict[str, str]) -> Dict[str, List[Any]]:
    """Build the canonical ``relations`` block from legacy string arrays.

    Word relations become ``[{"ref": <canonical id | None>, "headword": str}]``.
    Morphological relations stay as plain string lists.
    """
    relations: Dict[str, List[Any]] = {}
    for field in WORD_RELATION_FIELDS:
        items: List[Dict[str, Any]] = []
        seen = set()
        for entry in doc.get(field, []) or []:
            hw = _as_headword(entry).strip()
            if not hw:
                continue
            key = normalize_headword(hw)
            if key in seen:
                continue
            seen.add(key)
            items.append({"ref": id_by_key.get(key), "headword": hw})
        relations[field] = items
    for field in MORPH_FIELDS:
        relations[field] = [s for s in (doc.get(field, []) or []) if s]
    return relations


def build_meanings(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Backfill a one-entry ``meanings`` array from the existing flat fields.

    The array shape supports multiple meanings / parts of speech going forward
    without changing the flat ``simple_definition`` / ``part_of_speech`` fields
    that current consumers read.
    """
    examples = [e for e in [doc.get("example"), doc.get("easy_example")] if e]
    return [{
        "part_of_speech": doc.get("part_of_speech"),
        "definition": doc.get("simple_definition"),
        "easy_definition": doc.get("easy_meaning"),
        "detailed_definition": doc.get("detailed_definition"),
        "examples": examples,
        "cefr": doc.get("cefr"),
    }]


def build_pronunciation(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical US/UK pronunciation block backfilled from flat phonetics/audio."""
    audio = doc.get("audio") or {}
    return {
        "us": {
            "ipa": doc.get("phonetic_us") or doc.get("phonetic"),
            "audio": audio.get("us_url"),
        },
        "uk": {
            "ipa": doc.get("phonetic_uk") or doc.get("phonetic"),
            "audio": audio.get("uk_url"),
        },
    }


# Optional canonical fields that should always exist (capability placeholders).
# Only set when missing so existing data is never overwritten.
_OPTIONAL_DEFAULTS = {
    "confusing_words": list,
    "translations": dict,
    "school_relevance": list,
    "contextual_examples": list,
}


def to_canonical_storage(doc: Dict[str, Any], id_by_key: Dict[str, str]) -> Dict[str, Any]:
    """Return the ``$set`` payload that upgrades ``doc`` to the canonical schema.

    Additive and non-destructive: never removes or rewrites legacy fields; only
    computes ``canonical_key``/``relations`` and backfills structured
    capabilities (``meanings``/``pronunciation``) plus optional placeholders when
    they are absent. Preserves ``id`` and ``headword``.
    """
    out: Dict[str, Any] = {
        "canonical_key": normalize_headword(doc.get("headword")),
        "relations": build_relations(doc, id_by_key),
        "schema_version": SCHEMA_VERSION,
    }
    if not doc.get("meanings"):
        out["meanings"] = build_meanings(doc)
    if not doc.get("pronunciation"):
        out["pronunciation"] = build_pronunciation(doc)
    for field, factory in _OPTIONAL_DEFAULTS.items():
        if doc.get(field) is None:
            out[field] = factory()
    return out


def new_canonical_word(headword: str, definition: Dict[str, Any], *, provenance: str = "imported",
                       status: str = "PUBLISHED") -> Dict[str, Any]:
    """Build a complete canonical word document for a newly ingested headword.

    ``definition`` carries at least ``simple_definition`` and may include
    ``phonetic``/``example``/``part_of_speech`` (e.g. from a dictionary lookup).
    """
    hw = normalize_headword(headword)
    wid = canonical_id(headword)
    doc: Dict[str, Any] = {
        "id": wid,
        "headword": hw,
        "canonical_key": hw,
        "cefr": definition.get("cefr") or "B1",
        "topic": definition.get("topic") or "everyday",
        "frequency": definition.get("frequency", 3),
        "academic_importance": definition.get("academic_importance", 2),
        "exam_relevance": definition.get("exam_relevance", []),
        "synonyms": definition.get("synonyms", []),
        "antonyms": definition.get("antonyms", []),
        "related": definition.get("related", []),
        "simple_definition": definition.get("simple_definition"),
        "easy_meaning": definition.get("easy_meaning") or definition.get("simple_definition"),
        "phonetic": definition.get("phonetic"),
        "part_of_speech": definition.get("part_of_speech"),
        "example": definition.get("example"),
        "status": status,
        "provenance": provenance,
    }
    doc.update(to_canonical_storage(doc, {hw: wid}))
    return doc
