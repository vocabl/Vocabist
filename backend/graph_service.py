"""Canonical knowledge-graph service (Phase C).

Reusable relationship normalization, integrity checking, and one-hop graph
construction on top of the Phase A canonical schema.  Pure logic is DB-free and
portable; the ``async`` helpers accept a DatabaseRepository (mongo or supabase).

Relationship canonical form (Phase A):
    {"ref": "<canonical word id | null>", "headword": "<display headword>"}

Resolution priority for a relationship entry:
    1. an existing ``ref`` that points to a known canonical word
    2. ``canonical_key`` derived from the headword
    3. normalized-headword lookup (same map)
    4. unresolved  ->  ref = null

Never invents word IDs and never creates missing target words.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from vocab_schema import normalize_headword, WORD_RELATION_FIELDS, MORPH_FIELDS

LARGE_RELATION_THRESHOLD = 15


# --------------------------------------------------------------------------- #
# pure normalization / integrity
# --------------------------------------------------------------------------- #
def _entry_parts(entry: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return (headword, ref) from any historical entry shape."""
    if isinstance(entry, str):
        return entry, None
    if isinstance(entry, dict):
        return entry.get("headword") or entry.get("head") or None, entry.get("ref")
    return None, None


def _resolve_ref(entry_ref: Optional[str], hw_key: str,
                 id_by_key: Dict[str, str], known_ids: Set[str]) -> Optional[str]:
    if entry_ref and entry_ref in known_ids:
        return entry_ref
    by_key = id_by_key.get(hw_key)
    if by_key:
        return by_key
    return None


def _source_entries(doc: Dict[str, Any], field: str) -> Optional[List[Any]]:
    rels = doc.get("relations")
    if isinstance(rels, dict) and field in rels:
        return rels.get(field)
    return doc.get(field)


def normalize_relations(doc: Dict[str, Any], id_by_key: Dict[str, str],
                        known_ids: Set[str]) -> Tuple[Dict[str, List[Any]], Dict[str, int]]:
    """Deterministically normalize a word's relations.

    - resolves refs using the priority above
    - removes self-references
    - removes exact duplicate targets within a relation type (keeps first)
    - preserves unresolved targets as ``ref: null``
    - passes morphological fields (roots/prefixes/...) through unchanged
    Returns (normalized_relations, stats).
    """
    self_key = normalize_headword(doc.get("headword"))
    normalized: Dict[str, List[Any]] = {}
    stats = {"self_removed": 0, "duplicates_removed": 0, "malformed": 0,
             "resolved": 0, "unresolved": 0}

    for field in WORD_RELATION_FIELDS:
        entries = _source_entries(doc, field)
        if entries is None:
            normalized[field] = []
            continue
        if not isinstance(entries, list):
            stats["malformed"] += 1
            normalized[field] = []
            continue
        out: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for entry in entries:
            hw, ref = _entry_parts(entry)
            if hw is None or not str(hw).strip():
                stats["malformed"] += 1
                continue
            hw = str(hw).strip()
            hw_key = normalize_headword(hw)
            if not hw_key:
                stats["malformed"] += 1
                continue
            if hw_key == self_key and self_key:
                stats["self_removed"] += 1
                continue
            if hw_key in seen:
                stats["duplicates_removed"] += 1
                continue
            seen.add(hw_key)
            resolved = _resolve_ref(ref, hw_key, id_by_key, known_ids)
            if resolved:
                stats["resolved"] += 1
            else:
                stats["unresolved"] += 1
            out.append({"ref": resolved, "headword": hw})
        normalized[field] = out

    # morphological fields are strings; keep them verbatim
    rels = doc.get("relations") if isinstance(doc.get("relations"), dict) else {}
    for field in MORPH_FIELDS:
        val = rels.get(field, doc.get(field))
        normalized[field] = [s for s in (val or []) if s]

    return normalized, stats


def check_relationship_integrity(doc: Dict[str, Any], id_by_key: Dict[str, str],
                                 known_ids: Set[str]) -> Dict[str, Any]:
    """Structured integrity result for a word's relations (reusable by review)."""
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    self_key = normalize_headword(doc.get("headword"))
    rels = doc.get("relations") if isinstance(doc.get("relations"), dict) else {}

    # unknown relation types (only within an explicit relations object)
    for key in rels.keys():
        if key not in WORD_RELATION_FIELDS and key not in MORPH_FIELDS:
            errors.append({"code": "INVALID_RELATION_TYPE", "field": key,
                           "message": f"unknown relation type '{key}'"})

    for field in WORD_RELATION_FIELDS:
        entries = _source_entries(doc, field)
        if entries is None:
            continue
        if not isinstance(entries, list):
            errors.append({"code": "MALFORMED_RELATION", "field": field,
                           "message": f"{field} must be a list"})
            continue
        seen: Set[str] = set()
        for entry in entries:
            hw, ref = _entry_parts(entry)
            if hw is None or not str(hw).strip():
                errors.append({"code": "MALFORMED_RELATION", "field": field,
                               "message": f"empty/invalid entry: {entry!r}"})
                continue
            hw_key = normalize_headword(hw)
            if hw_key == self_key and self_key:
                errors.append({"code": "SELF_REFERENCE", "field": field,
                               "message": f"{field} references itself ('{hw}')"})
                continue
            if hw_key in seen:
                warnings.append({"code": "DUPLICATE_RELATION", "field": field,
                                 "message": f"duplicate target '{hw}'"})
            seen.add(hw_key)
            if ref and ref not in known_ids:
                warnings.append({"code": "BROKEN_RELATION_REF", "field": field,
                                 "message": f"ref '{ref}' not found"})
            elif not _resolve_ref(ref, hw_key, id_by_key, known_ids):
                warnings.append({"code": "UNRESOLVED_REF", "field": field,
                                 "message": f"'{hw}' has no canonical target"})

    normalized, _ = normalize_relations(doc, id_by_key, known_ids)
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "normalized_relations": normalized}


# --------------------------------------------------------------------------- #
# Repository-backed async helpers
# --------------------------------------------------------------------------- #

async def load_id_by_key(repo) -> Dict[str, str]:
    """Build headword-key → word-id map from the database."""
    words = await repo.load_all_words_minimal()
    id_by_key: Dict[str, str] = {}
    for w in words:
        k = normalize_headword(w.get("headword", ""))
        if k and k not in id_by_key:
            id_by_key[k] = w["id"]
    return id_by_key


async def build_word_graph(repo, word: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Bounded one-hop canonical graph for a word.

    Uses a single batch query instead of N individual DB lookups to avoid N+1
    performance problems, especially against Supabase HTTP.

    Deterministic order (input order), no duplicate nodes, no self-node,
    unresolved refs surfaced as ``{headword, id: null}``.
    """
    self_id = word.get("id")
    self_key = normalize_headword(word.get("headword"))
    rels = word.get("relations") if isinstance(word.get("relations"), dict) else {}

    # ── pass 1: collect all identifiers we'll need ──────────────────────────
    ref_ids: List[str] = []
    hw_keys: List[str] = []
    headwords_lower: List[str] = []

    for field in WORD_RELATION_FIELDS:
        entries = rels.get(field)
        if entries is None:
            entries = [{"ref": None, "headword": h} for h in (word.get(field, []) or [])]
        for entry in entries:
            hw, ref = _entry_parts(entry)
            if not hw or not str(hw).strip():
                continue
            hw_str = str(hw).strip()
            hw_key = normalize_headword(hw_str)
            if not hw_key or hw_key == self_key:
                continue
            if ref and ref not in ref_ids:
                ref_ids.append(ref)
            if hw_key not in hw_keys:
                hw_keys.append(hw_key)
            hw_lower = hw_str.lower()
            if hw_lower not in headwords_lower:
                headwords_lower.append(hw_lower)

    # ── pass 2: single batch fetch ───────────────────────────────────────────
    word_cache: Dict[str, Dict[str, Any]] = {}
    if ref_ids or hw_keys or headwords_lower:
        word_cache = await repo.load_words_for_graph_batch(ref_ids, hw_keys, headwords_lower)

    # ── pass 3: build graph using cached results ─────────────────────────────
    graph: Dict[str, List[Dict[str, Any]]] = {}
    for field in WORD_RELATION_FIELDS:
        entries = rels.get(field)
        if entries is None:
            entries = [{"ref": None, "headword": h} for h in (word.get(field, []) or [])]
        nodes: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for entry in entries:
            hw, ref = _entry_parts(entry)
            if not hw or not str(hw).strip():
                continue
            hw = str(hw).strip()
            hw_key = normalize_headword(hw)
            if not hw_key or hw_key == self_key:
                continue

            match: Optional[Dict[str, Any]] = None
            if ref:
                match = word_cache.get(f"ref:{ref}")
            if not match:
                match = (word_cache.get(f"hw_key:{hw_key}") or
                         word_cache.get(f"hw:{hw.lower()}"))

            node = match if match else {"headword": hw, "id": None}
            # strip _id if present (Mongo legacy)
            node = {k: v for k, v in node.items() if k != "_id"}

            if node.get("id") == self_id and self_id:
                continue
            dedupe_key = node["id"] if node.get("id") else f"hw:{hw_key}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            nodes.append(node)
        graph[field] = nodes

    return graph


async def resolve_all_relationship_refs(repo) -> Dict[str, int]:
    """Idempotent migration: normalize + resolve every word's relations.

    Only writes the ``relations`` field, and only when it actually changes.
    Never touches word IDs, definitions, progress, saved words, etc. Safe to
    run repeatedly (a second run reports 0 updated).
    """
    id_by_key = await load_id_by_key(repo)
    known_ids = set(id_by_key.values())
    words = await repo.load_all_words_full()
    stats = {"scanned": 0, "updated": 0, "self_removed": 0,
             "duplicates_removed": 0, "resolved": 0, "unresolved": 0}
    for w in words:
        stats["scanned"] += 1
        normalized, s = normalize_relations(w, id_by_key, known_ids)
        stats["self_removed"] += s["self_removed"]
        stats["duplicates_removed"] += s["duplicates_removed"]
        if w.get("relations") != normalized:
            await repo.update_word(w["id"], {"relations": normalized})
            stats["updated"] += 1

    # recompute resolved/unresolved for an accurate snapshot
    words_after = await repo.load_all_words_full()
    for w in words_after:
        for field in WORD_RELATION_FIELDS:
            for e in (w.get("relations", {}) or {}).get(field, []) or []:
                stats["resolved" if e.get("ref") else "unresolved"] += 1
    return stats


async def refresh_refs_for_new_key(repo, canonical_key: str, word_id: str) -> int:
    """Targeted re-resolution after a new word is ingested.

    Finds words whose relations reference ``canonical_key`` with a null ref and
    fills in ``word_id``. Uses the find_words_with_relation_headword repository
    method (RPC for Supabase, $elemMatch for Mongo).
    """
    if not canonical_key or not word_id:
        return 0
    candidates = await repo.find_words_with_relation_headword(canonical_key)
    updated = 0
    for w in candidates:
        if w.get("id") == word_id:
            continue
        rels = w.get("relations") or {}
        changed = False
        for field in WORD_RELATION_FIELDS:
            for e in rels.get(field, []) or []:
                if e.get("ref") is None and normalize_headword(e.get("headword")) == canonical_key:
                    e["ref"] = word_id
                    changed = True
        if changed:
            await repo.update_word(w["id"], {"relations": rels})
            updated += 1
    return updated


async def relationship_quality_metrics(repo) -> Dict[str, Any]:
    """Read-only relationship metrics for the content quality report."""
    id_by_key = await load_id_by_key(repo)
    known_ids = set(id_by_key.values())
    words = await repo.load_all_words_full()

    by_type = {f: 0 for f in WORD_RELATION_FIELDS}
    total = resolved = unresolved = self_refs = duplicates = malformed = 0
    words_no_rel = 0
    large_sets: List[Dict[str, Any]] = []

    for w in words:
        integ = check_relationship_integrity(w, id_by_key, known_ids)
        self_refs += sum(1 for e in integ["errors"] if e["code"] == "SELF_REFERENCE")
        malformed += sum(1 for e in integ["errors"] if e["code"] == "MALFORMED_RELATION")
        duplicates += sum(1 for e in integ["warnings"] if e["code"] == "DUPLICATE_RELATION")
        norm = integ["normalized_relations"]
        word_total = 0
        for field in WORD_RELATION_FIELDS:
            entries = norm.get(field, [])
            by_type[field] += len(entries)
            word_total += len(entries)
            for e in entries:
                total += 1
                resolved += 1 if e.get("ref") else 0
                unresolved += 0 if e.get("ref") else 1
        if word_total == 0:
            words_no_rel += 1
        if word_total > LARGE_RELATION_THRESHOLD:
            large_sets.append({"id": w["id"], "count": word_total})

    return {
        "total_relationships": total,
        "relationships_by_type": by_type,
        "resolved_refs": resolved,
        "unresolved_refs": unresolved,
        "self_references": self_refs,
        "duplicate_relationships": duplicates,
        "malformed_relationships": malformed,
        "words_with_no_relationships": words_no_rel,
        "words_with_large_relationship_sets": large_sets,
    }
