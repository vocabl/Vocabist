"""
DualWriteRepository — Failure Injection Test Suite
====================================================
Cases A-F as specified in the migration directive.

Run with:
    DB_BACKEND=dual DUAL_WRITE_ENABLED=true python3 tests/test_dual_write_failure_injection.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
import json
import traceback
from datetime import datetime, timezone

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

os.environ["DB_BACKEND"] = "dual"
os.environ["DUAL_WRITE_ENABLED"] = "true"

from db import reset_db_for_testing, get_db
from db.dual_write_repo import DualWriteRepository

RESULTS = []


def report(name: str, passed: bool, note: str):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"name": name, "status": status, "note": note})
    sym = "✓" if passed else "✗"
    print(f"  {sym} {name}: {status} — {note[:90]}")
    return passed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return f"dw_{uuid.uuid4().hex[:12]}"


async def _create_test_user(repo, user_id: str) -> None:
    email = f"{user_id}@dwtest.local"
    await repo._mongo._db.users.insert_one({
        "user_id": user_id, "email": email,
        "name": "DW Test", "tier": "free", "xp": 0, "streak": 0,
        "created_at": _now_iso(),
    })
    sb = await repo._supabase._client()
    await sb.table("users").upsert({
        "user_id": user_id, "email": email,
        "name": "DW Test", "tier": "free", "xp": 0, "streak": 0,
    }, on_conflict="user_id").execute()


async def _cleanup(repo, user_id: str) -> None:
    sb = await repo._supabase._client()
    db = repo._mongo._db
    for coll in ("users", "user_sessions", "saved_words", "user_word_progress", "profiles", "dual_write_outbox"):
        await db[coll].delete_many({"user_id": user_id})
    for tbl in ("user_sessions", "saved_words", "user_word_progress", "profiles", "users"):
        try:
            await sb.table(tbl).delete().eq("user_id", user_id).execute()
        except Exception:
            pass


# ============================================================================
# Case A: Both succeed → no new outbox entry
# ============================================================================
async def test_case_a_both_succeed():
    reset_db_for_testing()
    repo = get_db()
    assert isinstance(repo, DualWriteRepository)

    user_id = _uid()
    await _create_test_user(repo, user_id)

    session_token = _uid()
    doc = {
        "session_token": session_token,
        "user_id": user_id,
        "created_at": _now_iso(),
        "expires_at": "2030-01-01T00:00:00+00:00",
    }

    before = await repo._mongo._db.dual_write_outbox.count_documents({"resolved": False})
    await repo.create_session(doc)

    mongo_ok = (await repo._mongo._db.user_sessions.find_one(
        {"session_token": session_token}, {"_id": 0}
    )) is not None

    sb = await repo._supabase._client()
    r = await sb.table("user_sessions").select("*").eq(
        "session_token", session_token
    ).maybe_single().execute()
    sb_ok = r is not None and r.data is not None

    after = await repo._mongo._db.dual_write_outbox.count_documents({"resolved": False})

    await repo.delete_session(session_token)
    await _cleanup(repo, user_id)

    return report(
        "Case A: Mongo+Supabase succeed → no new outbox",
        mongo_ok and sb_ok and (after == before),
        f"mongo={mongo_ok} supabase={sb_ok} outbox_delta={after - before}"
    )


# ============================================================================
# Case B: Supabase fails → Mongo succeeds, outbox records failure
# ============================================================================
async def test_case_b_supabase_fails():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    before = await repo._mongo._db.dual_write_outbox.count_documents({"resolved": False})

    class _FakeTable:
        def upsert(self, *a, **kw): return self
        def insert(self, *a, **kw): return self
        def update(self, *a, **kw): return self
        def delete(self, *a, **kw): return self
        def select(self, *a, **kw): return self
        def eq(self, *a, **kw): return self
        def maybe_single(self): return self
        async def execute(self):
            raise RuntimeError("INJECTED: Supabase unavailable")

    class _FakeClient:
        def table(self, _): return _FakeTable()
        def rpc(self, *a, **kw): return _FakeTable()

    saved_sb = repo._supabase._sb
    repo._supabase._sb = _FakeClient()
    mongo_ok = False
    try:
        await repo.create_user({
            "user_id": user_id, "email": f"{user_id}@b.test",
            "name": "CaseB", "password_hash": "x",
            "tier": "free", "xp": 0, "streak": 0,
            "created_at": _now_iso(),
        })
        mongo_ok = True
    except Exception as e:
        return report("Case B", False, f"Mongo also failed: {e}")
    finally:
        repo._supabase._sb = saved_sb

    mongo_has = (await repo._mongo._db.users.find_one({"user_id": user_id}, {"_id": 0})) is not None
    after = await repo._mongo._db.dual_write_outbox.count_documents({"resolved": False})
    new_entries = after - before

    await repo._mongo._db.users.delete_one({"user_id": user_id})
    await repo._mongo._db.dual_write_outbox.delete_many({"user_id": user_id})

    return report(
        "Case B: Mongo OK + Supabase FAIL → Mongo persists, outbox recorded",
        mongo_ok and mongo_has and new_entries > 0,
        f"mongo_ok={mongo_ok} mongo_has_user={mongo_has} new_outbox={new_entries}"
    )


# ============================================================================
# Case C: Mongo fails → full op fails, Supabase NOT written
# ============================================================================
async def test_case_c_mongo_fails():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    original_coll = repo._mongo._db.users

    class _BrokenColl:
        async def insert_one(self, *a, **kw):
            raise RuntimeError("INJECTED: MongoDB write failed")
        def __getattr__(self, name):
            return getattr(original_coll, name)

    repo._mongo._db.__dict__["users"] = _BrokenColl()
    mongo_raised = False
    try:
        await repo.create_user({
            "user_id": user_id, "email": f"{user_id}@c.test",
            "name": "CaseC", "tier": "free", "xp": 0, "streak": 0,
            "created_at": _now_iso(),
        })
    except RuntimeError as e:
        mongo_raised = "INJECTED" in str(e)
    finally:
        del repo._mongo._db.__dict__["users"]

    sb = await repo._supabase._client()
    r = await sb.table("users").select("user_id").eq(
        "user_id", user_id
    ).maybe_single().execute()
    sb_not_written = r is None or r.data is None

    return report(
        "Case C: Mongo FAIL → op fails; Supabase NOT written",
        mongo_raised and sb_not_written,
        f"mongo_raised={mongo_raised} supabase_not_written={sb_not_written}"
    )


# ============================================================================
# Case D: Retry outbox entry succeeds → resolved
# ============================================================================
async def test_case_d_retry_succeeds():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    await _create_test_user(repo, user_id)
    await repo._mongo._db.dual_write_outbox.delete_many({"user_id": user_id})

    from db.dual_write_repo import _op_id, _now
    payload = {"user_id": user_id, "word_id": "abate", "created_at": _now_iso()}
    op = _op_id("saved_words", f"{user_id}:abate", payload)

    db = repo._mongo._db
    await db.dual_write_outbox.update_one(
        {"op_id": op},
        {"$setOnInsert": {
            "op_id": op, "collection": "saved_words", "operation": "upsert",
            "pk_field": "user_id,word_id", "pk_value": f"{user_id}:abate",
            "payload": payload, "user_id": user_id,
            "error": "INJECTED", "retry_count": 0, "resolved": False,
            "created_at": _now(), "resolved_at": None,
        }},
        upsert=True,
    )

    result = await repo.retry_outbox()
    entry = await db.dual_write_outbox.find_one({"op_id": op})
    resolved = entry is not None and entry.get("resolved") is True

    await db.dual_write_outbox.delete_one({"op_id": op})
    await _cleanup(repo, user_id)

    return report(
        "Case D: Outbox retry succeeds → entry resolved",
        resolved and result["resolved"] >= 1,
        f"resolved={resolved} retry_stats={result}"
    )


# ============================================================================
# Case E: Same operation twice → no duplicate in Supabase
# ============================================================================
async def test_case_e_idempotency():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    await _create_test_user(repo, user_id)

    await repo.save_word(user_id, "abate")
    await repo.save_word(user_id, "abate")  # idempotent

    sb = await repo._supabase._client()
    r = await sb.table("saved_words").select("*").eq("user_id", user_id).eq(
        "word_id", "abate"
    ).execute()
    sb_count = len(r.data) if r.data else 0

    mongo_docs = await repo._mongo._db.saved_words.find(
        {"user_id": user_id, "word_id": "abate"}, {"_id": 0}
    ).to_list(10)
    mongo_count = len(mongo_docs)

    await _cleanup(repo, user_id)

    return report(
        "Case E: save_word × 2 → 1 record each in Mongo & Supabase",
        sb_count == 1 and mongo_count == 1,
        f"mongo_count={mongo_count} supabase_count={sb_count}"
    )


# ============================================================================
# Case F: Restart recovery via outbox replay
# ============================================================================
async def test_case_f_restart_recovery():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    await _create_test_user(repo, user_id)
    await repo._mongo._db.dual_write_outbox.delete_many({"user_id": user_id})

    # Write to Mongo only (bypass DualWrite)
    await repo._mongo._db.saved_words.update_one(
        {"user_id": user_id, "word_id": "abate"},
        {"$set": {"user_id": user_id, "word_id": "abate", "created_at": _now_iso()}},
        upsert=True,
    )

    from db.dual_write_repo import _op_id, _now
    payload = {"user_id": user_id, "word_id": "abate", "created_at": _now_iso()}
    op = _op_id("saved_words", f"{user_id}:abate", payload)
    db = repo._mongo._db
    await db.dual_write_outbox.update_one(
        {"op_id": op},
        {"$setOnInsert": {
            "op_id": op, "collection": "saved_words", "operation": "upsert",
            "pk_field": "user_id,word_id", "pk_value": f"{user_id}:abate",
            "payload": payload, "user_id": user_id,
            "error": "SIMULATED: restart before mirror",
            "retry_count": 0, "resolved": False,
            "created_at": _now(), "resolved_at": None,
        }},
        upsert=True,
    )

    entry = await db.dual_write_outbox.find_one({"op_id": op})
    pre_unresolved = entry is not None and not entry.get("resolved", True)

    result = await repo.retry_outbox()

    sb = await repo._supabase._client()
    r = await sb.table("saved_words").select("*").eq("user_id", user_id).eq(
        "word_id", "abate"
    ).maybe_single().execute()
    sb_recovered = r is not None and r.data is not None

    entry_after = await db.dual_write_outbox.find_one({"op_id": op})
    resolved = entry_after is not None and entry_after.get("resolved") is True

    await db.dual_write_outbox.delete_one({"op_id": op})
    await _cleanup(repo, user_id)

    return report(
        "Case F: Restart recovery via outbox replay",
        pre_unresolved and sb_recovered and resolved,
        f"pre_unresolved={pre_unresolved} sb_recovered={sb_recovered} resolved={resolved}"
    )


# ============================================================================
# Idempotency — Progress (correct field names)
# ============================================================================
async def test_idempotency_progress():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    await _create_test_user(repo, user_id)

    doc = {
        "user_id": user_id, "word_id": "abate",
        "status": "SEEN",
        "times_seen": 1, "times_correct": 1, "times_wrong": 0,
        "consecutive_correct": 1,
        "mastery_score": 60.0, "confidence_score": 60.0, "difficulty": 0.5,
        "review_interval": 1,
        "average_response_time": 1500,
        "recent_results": [1],
        "next_review_at": _now_iso(),
        "last_reviewed_at": _now_iso(),
    }

    for _ in range(3):
        await repo.upsert_word_progress(user_id, "abate", doc)

    sb = await repo._supabase._client()
    r = await sb.table("user_word_progress").select("*").eq("user_id", user_id).eq(
        "word_id", "abate"
    ).execute()
    count = len(r.data) if r.data else 0

    await _cleanup(repo, user_id)

    return report(
        "Idempotency: upsert_word_progress × 3 → 1 record in Supabase",
        count == 1,
        f"supabase_count={count}"
    )


# ============================================================================
# XP increment
# ============================================================================
async def test_xp_increment():
    reset_db_for_testing()
    repo = get_db()

    user_id = _uid()
    await repo._mongo._db.users.insert_one({
        "user_id": user_id, "email": f"{user_id}@xp.test",
        "name": "XP", "tier": "free", "xp": 100, "streak": 0,
    })
    await repo._mongo._db.profiles.insert_one({
        "user_id": user_id, "xp": 100, "streak": 0, "longest_streak": 0,
    })
    sb = await repo._supabase._client()
    await sb.table("users").upsert({
        "user_id": user_id, "email": f"{user_id}@xp.test",
        "name": "XP", "tier": "free", "xp": 100, "streak": 0,
    }, on_conflict="user_id").execute()
    await sb.table("profiles").upsert({
        "user_id": user_id, "xp": 100, "streak": 0, "longest_streak": 0,
    }, on_conflict="user_id").execute()

    await repo.increment_user_xp(user_id, 25)

    mongo_u = await repo._mongo._db.users.find_one({"user_id": user_id}, {"_id": 0})
    mongo_xp = mongo_u.get("xp") if mongo_u else None

    r = await sb.table("users").select("xp").eq("user_id", user_id).maybe_single().execute()
    sb_xp = r.data.get("xp") if r and r.data else None

    await _cleanup(repo, user_id)

    return report(
        "XP increment: Mongo=125, Supabase=125",
        mongo_xp == 125 and sb_xp == 125,
        f"mongo_xp={mongo_xp} supabase_xp={sb_xp}"
    )


# ============================================================================
# Write-path audit
# ============================================================================
async def test_write_path_audit():
    dw = DualWriteRepository.__dict__
    required = [
        "create_user", "update_user",
        "create_profile", "update_profile",
        "create_session", "delete_session",
        "save_word", "unsave_word",
        "upsert_word_progress",
        "increment_user_xp",
        "complete_practice_session",
        "log_event",
        "insert_ai_coach_content", "insert_ai_coach_usage",
        "insert_tts_cache",
        "activate_subscription", "cancel_subscription",
        "update_word", "upsert_word",
    ]
    missing = [m for m in required if m not in dw]
    return report(
        "Write-path audit: all key mutations explicitly overridden",
        len(missing) == 0,
        f"missing={missing if missing else 'none'}"
    )


# ============================================================================
# Outbox inspect
# ============================================================================
async def test_outbox_inspect():
    reset_db_for_testing()
    repo = get_db()
    outbox = await repo.get_outbox_unresolved()
    result = await repo.retry_outbox()
    return report(
        "Outbox inspect/drain: no exception",
        True,
        f"unresolved={len(outbox)} retry={result}"
    )


# ============================================================================
# Main
# ============================================================================
async def main():
    print("\n" + "=" * 65)
    print("  DUAL-WRITE FAILURE INJECTION TESTS")
    print("=" * 65)

    tests = [
        ("Case A: Both Succeed", test_case_a_both_succeed),
        ("Case B: Supabase Fails", test_case_b_supabase_fails),
        ("Case C: Mongo Fails", test_case_c_mongo_fails),
        ("Case D: Retry Succeeds", test_case_d_retry_succeeds),
        ("Case E: Duplicate → No Dup", test_case_e_idempotency),
        ("Case F: Restart Recovery", test_case_f_restart_recovery),
        ("Idempotency: Progress", test_idempotency_progress),
        ("XP Increment", test_xp_increment),
        ("Write-Path Audit", test_write_path_audit),
        ("Outbox Inspect", test_outbox_inspect),
    ]

    for section, fn in tests:
        print(f"\n[{section}]")
        try:
            await fn()
        except Exception as e:
            report(section, False, f"UNCAUGHT: {type(e).__name__}: {e}")
            traceback.print_exc()

    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    total = len(RESULTS)

    print(f"\n{'=' * 65}")
    print(f"  FAILURE INJECTION RESULTS: PASS {passed}/{total}   FAIL {failed}")
    print("=" * 65)
    if failed:
        print("\nFAILED:")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"  ✗ {r['name']}: {r['note']}")

    out = {
        "backend": "dual", "test_type": "failure_injection",
        "passed": passed, "failed": failed, "total": total,
        "timestamp": _now_iso(), "results": RESULTS,
    }
    with open("/app/backend/tests/failure_injection_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
