"""Phase B — content ingestion & validation tests.

Layers:
1. Pure unit tests for content_validation (deterministic, no DB).
2. Async ingestion tests against a real Motor client (dedupe, provenance,
   lifecycle, AI-safety, idempotency).
3. API no-regression tests against the running backend.
"""
import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from content_validation import (  # noqa: E402
    validate_word,
    standardize_provenance,
    CEFR_VALUES,
)
from content_ingest import ingest_word, bulk_ingest, resolve_status, migrate_content_lifecycle  # noqa: E402

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://vocabist-restore.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _valid_word(**over):
    base = {
        "headword": "quixotic",
        "simple_definition": "extremely idealistic and unrealistic",
        "easy_meaning": "dreamy and impractical",
        "cefr": "C1",
        "topic": "academic",
        "part_of_speech": "adjective",
        "exam_relevance": [],
        "synonyms": ["idealistic"],
    }
    base.update(over)
    return base


# --------------------------- unit: validation ---------------------------
def test_valid_word_passes():
    res = validate_word(_valid_word())
    assert res.valid, res.errors
    assert res.normalized_data["canonical_key"] == "quixotic"


def test_normalization_case_and_whitespace():
    res = validate_word(_valid_word(headword="  Quixotic  "))
    assert res.valid
    assert res.normalized_data["canonical_key"] == "quixotic"
    assert res.normalized_data["headword"] == "quixotic"


def test_duplicate_canonical_key_rejected():
    res = validate_word(_valid_word(headword="Abate"), id_by_key={"abate": "abate"})
    assert not res.valid
    assert any(e["code"] == "DUPLICATE_CANONICAL_KEY" for e in res.errors)


def test_duplicate_key_allowed_for_self():
    res = validate_word(_valid_word(headword="Abate"), id_by_key={"abate": "abate"}, existing_id="abate")
    assert res.valid


def test_missing_definition_rejected():
    res = validate_word(_valid_word(simple_definition="", meanings=None))
    assert not res.valid
    assert any(e["code"] == "MISSING_DEFINITION" for e in res.errors)


def test_invalid_cefr_rejected():
    res = validate_word(_valid_word(cefr="Z9"))
    assert not res.valid
    assert any(e["code"] == "INVALID_CEFR" for e in res.errors)
    # missing CEFR is a warning, not an error
    res2 = validate_word(_valid_word(cefr=None))
    assert res2.valid
    assert any(w["code"] == "MISSING_CEFR" for w in res2.warnings)


def test_self_reference_detected():
    res = validate_word(_valid_word(synonyms=["quixotic"]))
    assert not res.valid
    assert any(e["code"] == "SELF_REFERENCE" for e in res.errors)


def test_duplicate_relationship_warned():
    res = validate_word(_valid_word(synonyms=["idealistic", "Idealistic"]))
    assert res.valid
    assert any(w["code"] == "DUPLICATE_RELATION" for w in res.warnings)


def test_malformed_relation_rejected():
    res = validate_word(_valid_word(synonyms=[{"no_headword": 1}]))
    assert not res.valid
    assert any(e["code"] == "MALFORMED_RELATION" for e in res.errors)


def test_invalid_exam_reference_rejected():
    res = validate_word(_valid_word(exam_relevance=["not-a-real-exam"]),
                        known_exam_slugs={"ielts", "toefl"})
    assert not res.valid
    assert any(e["code"] == "INVALID_EXAM_REF" for e in res.errors)
    # verifiable + valid
    ok = validate_word(_valid_word(exam_relevance=["ielts"]), known_exam_slugs={"ielts"})
    assert ok.valid


def test_invalid_provenance_and_status_rejected():
    assert not validate_word(_valid_word(provenance="NONSENSE")).valid
    assert not validate_word(_valid_word(status="LIVE")).valid


def test_malformed_pronunciation_rejected():
    res = validate_word(_valid_word(pronunciation={"us": "not-a-dict"}))
    assert not res.valid
    assert any(e["code"] == "MALFORMED_PRONUNCIATION" for e in res.errors)


def test_standardize_provenance_maps_legacy():
    assert standardize_provenance("seed") == "CURATED"
    assert standardize_provenance("ai_generated") == "AI_GENERATED"
    assert standardize_provenance("imported") == "IMPORTED"
    assert standardize_provenance("AI_GENERATED") == "AI_GENERATED"
    assert standardize_provenance("bogus") is None


def test_resolve_status_ai_never_published():
    class R:
        warnings = []
    assert resolve_status("AI_GENERATED", R(), "PUBLISHED") == "REVIEW"
    assert resolve_status("IMPORTED", R(), None) == "PUBLISHED"
    assert resolve_status("CURATED", R(), "PUBLISHED") == "PUBLISHED"

    class RW:
        warnings = [{"code": "MISSING_CEFR"}]
    assert resolve_status("CURATED", RW(), "PUBLISHED") == "REVIEW"


# --------------------------- async: ingestion ---------------------------
import asyncio  # noqa: E402


def _run_with_repo(body):
    """Run an async test body with a MongoRepository (new API) + raw Motor db
    for direct verification queries.  Both are passed to body(repo, raw_db).
    """
    async def _wrap():
        from motor.motor_asyncio import AsyncIOMotorClient
        from db.mongo_repo import MongoRepository
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        raw_db = client[os.environ.get("DB_NAME", "vocably")]
        repo = MongoRepository()
        try:
            return await body(repo, raw_db)
        finally:
            client.close()
    return asyncio.run(_wrap())


# Keep backward alias for graph_service tests that still pass (db, ...) directly.
def _run_with_db(body):
    return _run_with_repo(lambda repo, db: body(db))


def test_ingest_dedupes_existing():
    async def body(repo, db):
        out = await ingest_word(repo, {"headword": "ABATE", "simple_definition": "x"},
                                provenance="ADMIN_CREATED")
        assert out["action"] == "exists"
        assert out["id"] == "abate"
    _run_with_repo(body)


def test_ingest_ai_enters_review_and_is_idempotent():
    async def body(repo, db):
        hw = f"zztest{uuid.uuid4().hex[:8]}"
        rec = {"headword": hw, "simple_definition": "a synthetic test word", "cefr": "B2", "topic": "test"}
        try:
            out1 = await ingest_word(repo, rec, provenance="AI_GENERATED", requested_status="PUBLISHED")
            assert out1["action"] == "created"
            assert out1["status"] == "REVIEW"  # AI never auto-publishes
            assert await db.words.count_documents({"id": out1["id"], "status": "PUBLISHED"}) == 0
            out2 = await ingest_word(repo, rec, provenance="AI_GENERATED")
            assert out2["action"] == "exists" and out2["id"] == out1["id"]
        finally:
            await db.words.delete_one({"headword": hw})
    _run_with_repo(body)


def test_ingest_rejects_invalid_without_writing():
    async def body(repo, db):
        hw = f"zzbad{uuid.uuid4().hex[:8]}"
        out = await ingest_word(repo, {"headword": hw, "cefr": "ZZ"}, provenance="ADMIN_CREATED")
        assert out["action"] == "rejected"
        assert await db.words.count_documents({"headword": hw}) == 0
    _run_with_repo(body)


def test_bulk_ingest_reports_per_record():
    async def body(repo, db):
        prefix = f"zzblk{uuid.uuid4().hex[:6]}"
        records = [
            {"headword": f"{prefix}one", "simple_definition": "def one", "cefr": "B1", "topic": "t"},
            {"headword": f"{prefix}one", "simple_definition": "dup"},          # duplicate within batch
            {"headword": f"{prefix}bad", "cefr": "NOPE"},                       # invalid
        ]
        try:
            summary = await bulk_ingest(repo, records, provenance="AI_GENERATED")
            assert summary["total"] == 3
            assert summary["created"] == 1
            assert summary["exists"] == 1
            assert summary["rejected"] == 1
        finally:
            await db.words.delete_many({"headword": {"$regex": f"^{prefix}"}})
    _run_with_repo(body)


def test_lifecycle_migration_idempotent_and_nondestructive():
    async def body(repo, db):
        # existing words are standardized + PUBLISHED, never downgraded
        assert await migrate_content_lifecycle(repo) == 0  # already migrated at startup
        a = await db.words.find_one({"id": "abate"},
                                    {"_id": 0, "status": 1, "provenance": 1, "lifecycle_version": 1})
        assert a["status"] == "PUBLISHED"
        assert a["provenance"] in {"CURATED", "AI_GENERATED", "IMPORTED", "ADMIN_CREATED"}
        assert a["lifecycle_version"] == 1
    _run_with_repo(body)  # body uses both repo (for lifecycle) and raw db (for verification)


# --------------------------- API no-regression ---------------------------
@pytest.fixture(scope="module")
def headers():
    email = f"phaseb_{uuid.uuid4().hex[:10]}@vocabist.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123", "name": "PhaseB"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


def test_api_import_still_returns_existing(headers):
    r = requests.post(f"{API}/words/import", json={"headword": "Abate"}, headers=headers, timeout=30)
    assert r.status_code == 200 and r.json()["id"] == "abate"


def test_api_word_detail_and_bank_size(headers):
    r = requests.get(f"{API}/words?limit=1", headers=headers, timeout=30)
    assert r.status_code == 200
    assert r.json()["total"] >= 231  # existing published bank remains usable
    d = requests.get(f"{API}/words/abate", headers=headers, timeout=30)
    assert d.status_code == 200 and d.json()["word"]["status"] == "PUBLISHED"


def test_api_practice_still_works(headers):
    r = requests.post(f"{API}/practice/start?source=word&ref=abate", headers=headers, timeout=30)
    assert r.status_code == 200 and r.json()["count"] >= 1
