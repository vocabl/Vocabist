"""Phase C — knowledge graph + relationship integrity tests.

Layers:
1. Pure unit tests for graph_service normalization/integrity (no DB).
2. Async tests (Motor via asyncio.run) for migration idempotency, targeted
   re-resolution, and the graph builder.
3. API no-regression tests against the running backend.
"""
import os
import sys
import uuid
import asyncio

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from graph_service import (  # noqa: E402
    normalize_relations,
    check_relationship_integrity,
    build_word_graph,
    resolve_all_relationship_refs,
    refresh_refs_for_new_key,
    relationship_quality_metrics,
)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://learn-preview-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ID_BY_KEY = {"increase": "increase", "diminish": "diminish", "delivery": "delivery"}
KNOWN = set(ID_BY_KEY.values())


def _run_with_db(body):
    async def _wrap():
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ.get("DB_NAME", "vocably")]
        try:
            return await body(db)
        finally:
            client.close()
    return asyncio.run(_wrap())


# ------------------------- A. canonical resolution -------------------------
def test_resolution_priority_ref_then_key_then_headword():
    doc = {"headword": "abate", "relations": {"synonyms": [
        {"ref": "increase", "headword": "increase"},   # valid existing ref
        {"ref": None, "headword": "Diminish"},          # resolved via canonical_key
        {"ref": None, "headword": "Nowhereword"},       # unresolved -> null
    ]}}
    norm, stats = normalize_relations(doc, ID_BY_KEY, KNOWN)
    syn = norm["synonyms"]
    assert syn[0]["ref"] == "increase"
    assert syn[1]["ref"] == "diminish" and syn[1]["headword"] == "Diminish"
    assert syn[2]["ref"] is None
    assert stats["resolved"] == 2 and stats["unresolved"] == 1


def test_stale_ref_falls_back_to_key():
    doc = {"headword": "abate", "relations": {"antonyms": [
        {"ref": "ghost-id", "headword": "increase"},   # stale ref not in known ids
    ]}}
    norm, _ = normalize_relations(doc, ID_BY_KEY, KNOWN)
    assert norm["antonyms"][0]["ref"] == "increase"


def test_case_and_whitespace_normalization_and_legacy_strings():
    doc = {"headword": "abate", "synonyms": ["  Increase  ", "increase"]}  # legacy strings, dup by case
    norm, stats = normalize_relations(doc, ID_BY_KEY, KNOWN)
    assert len(norm["synonyms"]) == 1
    assert norm["synonyms"][0]["ref"] == "increase"
    assert stats["duplicates_removed"] == 1


# ------------------------- B. integrity -------------------------
def test_self_reference_removed_and_flagged():
    doc = {"headword": "order", "relations": {"related": [
        {"ref": "order", "headword": "order"}, {"ref": None, "headword": "delivery"}]}}
    norm, stats = normalize_relations(doc, ID_BY_KEY, KNOWN)
    assert [e["headword"] for e in norm["related"]] == ["delivery"]
    assert stats["self_removed"] == 1
    integ = check_relationship_integrity(doc, ID_BY_KEY, KNOWN)
    assert not integ["valid"]
    assert any(e["code"] == "SELF_REFERENCE" for e in integ["errors"])


def test_malformed_relationship_detected():
    doc = {"headword": "abate", "relations": {"synonyms": [{"no_headword": 1}, ""]}}
    integ = check_relationship_integrity(doc, ID_BY_KEY, KNOWN)
    assert not integ["valid"]
    assert any(e["code"] == "MALFORMED_RELATION" for e in integ["errors"])


def test_cross_relation_same_target_allowed():
    doc = {"headword": "abate", "relations": {
        "synonyms": [{"ref": "increase", "headword": "increase"}],
        "antonyms": [{"ref": "increase", "headword": "increase"}]}}
    norm, _ = normalize_relations(doc, ID_BY_KEY, KNOWN)
    assert norm["synonyms"][0]["ref"] == "increase"
    assert norm["antonyms"][0]["ref"] == "increase"  # same target across types is fine


def test_unresolved_ref_is_detectable():
    doc = {"headword": "abate", "relations": {"related": [{"ref": None, "headword": "delivery"}]}}
    # delivery resolves here; use an unknown headword to force unresolved
    doc2 = {"headword": "abate", "relations": {"related": [{"ref": None, "headword": "zzunknown"}]}}
    integ = check_relationship_integrity(doc2, ID_BY_KEY, KNOWN)
    assert any(w["code"] == "UNRESOLVED_REF" for w in integ["warnings"])


# ------------------------- C. migration (async) -------------------------
def test_migration_idempotent_and_repaired_self_refs():
    def body(db):
        async def inner():
            # startup already ran it; a fresh run must not change anything
            stats = await resolve_all_relationship_refs(db)
            assert stats["updated"] == 0, f"expected idempotent, got {stats}"
            # the 4 historical self-refs are gone; legit targets preserved
            for wid, kept in [("order", "delivery"), ("schedule", "calendar"),
                              ("encounter", "encountered"), ("postulate", "assumption")]:
                w = await db.words.find_one({"id": wid}, {"_id": 0, "relations": 1})
                rel = w["relations"]["related"]
                assert all((e["headword"] or "").lower() != wid for e in rel)
                assert any(e["headword"] == kept for e in rel)
            return True
        return inner()
    assert _run_with_db(body)


def test_migration_preserves_ids_and_progress_counts():
    def body(db):
        async def inner():
            before_ids = await db.words.count_documents({})
            before_prog = await db.user_word_progress.count_documents({})
            before_saved = await db.saved_words.count_documents({})
            await resolve_all_relationship_refs(db)
            assert await db.words.count_documents({}) == before_ids
            assert await db.user_word_progress.count_documents({}) == before_prog
            assert await db.saved_words.count_documents({}) == before_saved
            return True
        return inner()
    assert _run_with_db(body)


def test_targeted_refresh_resolves_new_key():
    def body(db):
        async def inner():
            src = f"zzsrc{uuid.uuid4().hex[:6]}"
            tgt = f"zztgt{uuid.uuid4().hex[:6]}"
            # a word that relates to a not-yet-existing target (ref null)
            await db.words.insert_one({
                "id": src, "headword": src, "canonical_key": src, "status": "PUBLISHED",
                "simple_definition": "x", "provenance": "CURATED",
                "relations": {"synonyms": [{"ref": None, "headword": tgt}],
                              "antonyms": [], "related": [], "confusing_words": []}})
            try:
                # now the target canonical word appears
                updated = await refresh_refs_for_new_key(db, tgt, tgt)
                assert updated == 1
                w = await db.words.find_one({"id": src}, {"_id": 0, "relations": 1})
                assert w["relations"]["synonyms"][0]["ref"] == tgt
            finally:
                await db.words.delete_one({"id": src})
            return True
        return inner()
    assert _run_with_db(body)


# ------------------------- D. graph service (async) -------------------------
def test_graph_builder_no_dupes_no_self():
    def body(db):
        async def inner():
            w = await db.words.find_one({"id": "abate"}, {"_id": 0})
            g = await build_word_graph(db, w)
            for field in ("synonyms", "antonyms", "related", "confusing_words"):
                assert field in g
                ids = [n["id"] for n in g[field] if n.get("id")]
                assert len(ids) == len(set(ids))                 # no duplicate nodes
                assert "abate" not in ids                         # no self node
                for n in g[field]:
                    assert "headword" in n and "id" in n          # graceful unresolved
            return True
        return inner()
    assert _run_with_db(body)


def test_relationship_metrics_shape():
    def body(db):
        async def inner():
            m = await relationship_quality_metrics(db)
            assert m["self_references"] == 0
            assert set(m["relationships_by_type"]) == {"synonyms", "antonyms", "related", "confusing_words"}
            assert m["resolved_refs"] + m["unresolved_refs"] == m["total_relationships"]
            return True
        return inner()
    assert _run_with_db(body)


# ------------------------- E. API regression -------------------------
@pytest.fixture(scope="module")
def headers():
    email = f"phasec_{uuid.uuid4().hex[:10]}@vocabist.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123", "name": "PhaseC"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


def test_word_detail_graph_shape_preserved(headers):
    r = requests.get(f"{API}/words/abate", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    g = r.json()["graph"]
    for field in ("synonyms", "antonyms", "related", "confusing_words"):
        assert field in g
        for n in g[field]:
            assert "headword" in n and "id" in n
    # antonym 'increase' resolves to a real canonical id
    assert {e["headword"]: e["id"] for e in g["antonyms"]}.get("increase") == "increase"


def test_repaired_word_detail_no_self_node(headers):
    r = requests.get(f"{API}/words/order", headers=headers, timeout=30)
    assert r.status_code == 200
    g = r.json()["graph"]
    for field in ("synonyms", "antonyms", "related", "confusing_words"):
        assert all((n["headword"] or "").lower() != "order" for n in g[field])


def test_saved_and_practice_unaffected(headers):
    requests.post(f"{API}/words/abate/save", headers=headers, timeout=30)
    s = requests.get(f"{API}/saved", headers=headers, timeout=30)
    assert s.status_code == 200 and any(w["id"] == "abate" for w in s.json()["words"])
    requests.delete(f"{API}/words/abate/save", headers=headers, timeout=30)
    p = requests.post(f"{API}/practice/start?source=word&ref=abate", headers=headers, timeout=30)
    assert p.status_code == 200 and p.json()["count"] >= 1


def test_import_unaffected(headers):
    r = requests.post(f"{API}/words/import", json={"headword": "Abate"}, headers=headers, timeout=30)
    assert r.status_code == 200 and r.json()["id"] == "abate"
