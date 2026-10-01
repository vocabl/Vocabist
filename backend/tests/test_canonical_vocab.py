"""Phase A — canonical vocabulary architecture tests.

Two layers:
1. Pure unit tests for vocab_schema (no DB, deterministic).
2. API tests against the running backend for canonical identity, relation
   resolution to canonical refs, duplicate prevention, and no-regression of
   Word Detail / Saved / Practice.
"""
import os
import sys
import uuid

import requests
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vocab_schema import (  # noqa: E402
    normalize_headword,
    canonical_id,
    build_relations,
    build_meanings,
    build_pronunciation,
    to_canonical_storage,
    new_canonical_word,
)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://learn-preview-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ----------------------------- unit: schema -----------------------------
def test_normalize_headword_collapses_case_space_punctuation():
    assert normalize_headword("  Abate  ") == "abate"
    assert normalize_headword("ABATE.") == "abate"
    assert normalize_headword("Well  Being") == "well being"
    assert normalize_headword("café!") == "caf"  # non-ascii stripped, deterministic
    assert normalize_headword(None) == ""


def test_canonical_id_is_slug_like_and_stable():
    assert canonical_id("Abate") == "abate"
    assert canonical_id("well being") == "well-being"
    assert canonical_id("well-being") == "well-being"


def test_build_relations_resolves_refs_and_keeps_headwords():
    doc = {"synonyms": ["Lessen", "Diminish", "lessen"], "antonyms": ["Increase"],
           "roots": ["battre"], "word_family": ["abatement"]}
    id_by_key = {"increase": "increase", "diminish": "diminish"}
    rel = build_relations(doc, id_by_key)
    # de-duped, ref resolved where known, headword preserved
    syn = rel["synonyms"]
    assert [s["headword"] for s in syn] == ["Lessen", "Diminish"]
    assert next(s for s in syn if s["headword"] == "Diminish")["ref"] == "diminish"
    assert next(s for s in syn if s["headword"] == "Lessen")["ref"] is None
    assert rel["antonyms"][0]["ref"] == "increase"
    # morphological fields stay plain strings
    assert rel["roots"] == ["battre"]
    assert rel["word_family"] == ["abatement"]
    assert rel["confusing_words"] == []


def test_build_meanings_and_pronunciation_backfill():
    doc = {"part_of_speech": "verb", "simple_definition": "to lessen",
           "easy_meaning": "get smaller", "example": "It abated.", "easy_example": "rain abated",
           "cefr": "C1", "phonetic_us": "/us/", "phonetic_uk": "/uk/"}
    m = build_meanings(doc)
    assert len(m) == 1 and m[0]["definition"] == "to lessen"
    assert m[0]["examples"] == ["It abated.", "rain abated"]
    p = build_pronunciation(doc)
    assert p["us"]["ipa"] == "/us/" and p["uk"]["ipa"] == "/uk/"


def test_to_canonical_storage_is_additive_and_versioned():
    doc = {"id": "abate", "headword": "abate", "simple_definition": "x", "synonyms": ["increase"]}
    out = to_canonical_storage(doc, {"increase": "increase"})
    assert out["canonical_key"] == "abate"
    assert out["schema_version"] == 1
    assert out["relations"]["synonyms"][0]["ref"] == "increase"
    # does not touch id/headword
    assert "id" not in out and "headword" not in out


def test_new_canonical_word_is_complete():
    doc = new_canonical_word("Serendipity", {"simple_definition": "lucky find", "phonetic": "/s/"})
    assert doc["id"] == "serendipity" and doc["headword"] == "serendipity"
    assert doc["canonical_key"] == "serendipity"
    assert doc["status"] == "PUBLISHED" and doc["provenance"] == "imported"
    assert doc["relations"]["synonyms"] == []
    assert doc["meanings"][0]["definition"] == "lucky find"


# ----------------------------- API fixtures -----------------------------
@pytest.fixture(scope="module")
def headers():
    email = f"canon_{uuid.uuid4().hex[:10]}@vocabist.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123", "name": "Canon Test"}, timeout=30)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


# ----------------------------- API: canonical identity -----------------------------
def test_word_detail_has_canonical_schema(headers):
    r = requests.get(f"{API}/words/abate", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    w = r.json()["word"]
    assert w["id"] == "abate"
    assert w["canonical_key"] == "abate"
    assert w["schema_version"] == 1
    assert isinstance(w["meanings"], list) and w["meanings"]
    assert "us" in w["pronunciation"] and "uk" in w["pronunciation"]
    assert "relations" in w


def test_graph_resolves_to_canonical_refs(headers):
    r = requests.get(f"{API}/words/abate", headers=headers, timeout=30)
    graph = r.json()["graph"]
    # response shape preserved
    for key in ("synonyms", "antonyms", "related"):
        assert key in graph
        for entry in graph[key]:
            assert "headword" in entry and "id" in entry
    # additive confusing_words present
    assert "confusing_words" in graph
    # a resolvable antonym gets a real canonical id (increase is in the bank)
    anto = {e["headword"]: e["id"] for e in graph["antonyms"]}
    assert anto.get("increase") == "increase"


def test_duplicate_prevention_returns_existing_canonical(headers):
    # importing an existing headword in a different case must not create a 2nd word
    r = requests.post(f"{API}/words/import", json={"headword": "ABATE"}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "abate"


def test_saved_words_still_work(headers):
    requests.post(f"{API}/words/abate/save", headers=headers, timeout=30)
    r = requests.get(f"{API}/saved", headers=headers, timeout=30)
    assert r.status_code == 200
    assert any(w["id"] == "abate" for w in r.json()["words"])
    requests.delete(f"{API}/words/abate/save", headers=headers, timeout=30)


def test_practice_start_still_builds_questions(headers):
    r = requests.post(f"{API}/practice/start?source=word&ref=abate", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] >= 1
    q = data["questions"][0]
    assert q["word_id"] == "abate" and q["mode"] and "card" in q
