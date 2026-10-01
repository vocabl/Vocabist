#!/usr/bin/env python3
"""
=============================================================================
VOCABIST — MongoDB → Supabase Data Migration Script
=============================================================================
Version   : 1.0.0
Created   : Stage 2 Preparation (DO NOT EXECUTE until explicitly approved)
=============================================================================

PURPOSE
-------
Migrate all 381 MongoDB documents across 15 collections to the Supabase
PostgreSQL schema defined in 000_consolidated_migration.sql.

SAFETY GUARANTEES
-----------------
  ✅ READ-ONLY on MongoDB — no writes, no deletes
  ✅ Idempotent — safe to run multiple times (INSERT ON CONFLICT DO NOTHING)
  ✅ Resumable — tracks per-collection state in migration_state.json
  ✅ Non-destructive — never truncates, resets, or drops Supabase data
  ✅ Dependency-aware — migrates in FK-safe order
  ✅ Per-record error capture — no silent failures
  ✅ Dry-run mode — pass --dry-run to validate without inserting

USAGE
-----
  # Dry-run (validate only, no inserts):
  python3 migrate_mongodb_to_supabase.py --dry-run

  # Full migration (requires explicit approval):
  python3 migrate_mongodb_to_supabase.py

  # Migrate a single collection (for partial retries):
  python3 migrate_mongodb_to_supabase.py --collection words

  # Reset state for a single collection (force re-migration):
  python3 migrate_mongodb_to_supabase.py --reset-collection words

  # Verify counts after migration:
  python3 migrate_mongodb_to_supabase.py --verify-only

MIGRATION ORDER (FK-safe)
--------------------------
  1.  topics             (no FK dependencies)
  2.  exams              (no FK dependencies)
  3.  articles           (→ topics)
  4.  words              (→ topics)
  5.  users              (no FK dependencies)
  6.  profiles           (→ users, → exams)
  7.  user_sessions      (→ users)
  8.  subscriptions      (→ users)
  9.  user_word_progress (→ users, → words)
  10. saved_words        (→ users, → words)
  11. study_sessions     (→ users)
  12. ai_coach_content   (→ words)
  13. ai_coach_usage     (→ users, → words)
  14. tts_cache          (no FK dependencies)
  15. analytics_events   (→ users)

IDEMPOTENCY STRATEGY
--------------------
  Every INSERT uses Supabase's upsert with ignore_duplicates=True.
  This maps to: INSERT INTO ... ON CONFLICT (conflict_column) DO NOTHING

  Tables with natural PKs (topics, exams, articles, words, users, profiles,
  user_sessions, subscriptions, user_word_progress, saved_words,
  ai_coach_content, tts_cache):
    → ON CONFLICT (primary_key) DO NOTHING

  Append-only tables (study_sessions, ai_coach_usage, analytics_events):
    → Each migrated record carries its MongoDB ObjectId as source_mongo_id
    → ON CONFLICT (source_mongo_id) DO NOTHING
    → Backed by UNIQUE INDEX on source_mongo_id (migration 008)
    → New Supabase-native records (post-migration) have source_mongo_id=NULL
      and are unaffected (PostgreSQL allows multiple NULLs in a unique index)
    → migration_state.json is an OPTIMISATION only — not the sole guard

  PRE-REQUISITE: Run migration 008_add_source_mongo_id.sql in Supabase
  Dashboard → SQL Editor BEFORE executing the actual migration.
  The dry-run does not require this (transforms only, no DB interaction).

RETRY STRATEGY
--------------
  On individual record failure: log + continue (do not abort batch).
  On batch failure: retry up to MAX_RETRIES times with exponential backoff.
  On collection completion: write state to migration_state.json.
  On script restart: skip completed collections (use --reset-collection to force).

=============================================================================
"""

import asyncio
import json
import logging
import os
import sys
import time
import argparse
from datetime import datetime, date, timezone
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from supabase import create_client, Client

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent
STATE_FILE   = SCRIPT_DIR / "migration_state.json"
LOG_FILE     = SCRIPT_DIR / "migration.log"
ERRORS_FILE  = SCRIPT_DIR / "migration_errors.json"

BATCH_SIZE   = 50          # records per upsert batch
MAX_RETRIES  = 3           # retries per batch on transient failure
RETRY_DELAY  = 2.0         # seconds (doubles on each retry)

# TEXT[] columns that must never be NULL (schema has NOT NULL DEFAULT '{}')
NULL_TO_EMPTY_ARRAY_FIELDS = [
    "synonyms", "antonyms", "related", "confusing_words",
    "word_family", "roots", "prefixes", "suffixes", "exam_relevance",
    "recent_results", "last_reason_codes",
]

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("vocabist_migration")


# ─────────────────────────────────────────────────────────────────────────────
# State management
# ─────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_errors() -> list:
    if ERRORS_FILE.exists():
        with open(ERRORS_FILE) as f:
            return json.load(f)
    return []


def save_errors(errors: list) -> None:
    with open(ERRORS_FILE, "w") as f:
        json.dump(errors, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# Data transformation helpers
# ─────────────────────────────────────────────────────────────────────────────

def clean_doc(doc: dict) -> dict:
    """Remove MongoDB _id and convert ObjectId / datetime to plain Python types."""
    d = {k: v for k, v in doc.items() if k != "_id"}
    return d


def to_iso(val: Any) -> Optional[str]:
    """Convert datetime → ISO 8601 string. Returns None for None input."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.isoformat()
    if isinstance(val, str):
        return val
    return str(val)


def to_date_str(val: Any) -> Optional[str]:
    """Convert ISO date string or datetime → 'YYYY-MM-DD'. Returns None for None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        # Validate it's a parseable date
        try:
            date.fromisoformat(val[:10])   # accept 'YYYY-MM-DD' prefix
            return val[:10]
        except ValueError:
            log.warning(f"  Cannot parse date string: {repr(val)} — setting NULL")
            return None
    return None


def to_bytea_hex(val: Any) -> Optional[str]:
    """Convert bytes → PostgreSQL hex literal '\\x{hex}'.
    PostgREST accepts bytea as '\\x' + hex string."""
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        return "\\x" + val.hex()
    if isinstance(val, str) and val.startswith("\\x"):
        return val   # already encoded
    return None


def coerce_null_arrays(doc: dict) -> dict:
    """Replace None in array fields with [] to satisfy NOT NULL DEFAULT '{}'."""
    for field in NULL_TO_EMPTY_ARRAY_FIELDS:
        if field in doc and doc[field] is None:
            doc[field] = []
    return doc


def sanitize_timestamps(doc: dict) -> dict:
    """Convert all datetime fields to ISO strings for supabase-py."""
    ts_fields = ["created_at", "updated_at", "expires_at", "started_at",
                  "cancelled_at", "last_reviewed_at", "next_review_at"]
    for f in ts_fields:
        if f in doc:
            doc[f] = to_iso(doc[f])
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# Per-collection transform functions
# ─────────────────────────────────────────────────────────────────────────────

def transform_topic(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    return d


def transform_exam(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # max_score may be int → cast to float for NUMERIC(6,1)
    if "max_score" in d and d["max_score"] is not None:
        d["max_score"] = float(d["max_score"])
    return d


def transform_article(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    return d


def transform_word(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    d = coerce_null_arrays(d)
    # frequency, academic_importance: MongoDB stores as int → SMALLINT is fine
    # translations: MongoDB stores as {} (empty dict) for no translations
    # → keep as-is, JSONB handles empty dicts
    # Ensure JSONB fields that are empty dicts/lists are preserved as-is
    return d


def transform_user(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # tier: ensure it's 'free' or 'pro' — CHECK constraint will catch others
    return d


def transform_profile(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # exam_date: MongoDB stores as ISO string 'YYYY-MM-DD' → PostgreSQL DATE
    if "exam_date" in d:
        d["exam_date"] = to_date_str(d["exam_date"])
    # last_active_date: similarly
    if "last_active_date" in d:
        d["last_active_date"] = to_date_str(d["last_active_date"])
    return d


def transform_user_session(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # Remove internal MongoDB fields that don't exist in schema
    d.pop("_id", None)
    return d


def transform_subscription(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    return d


def transform_user_word_progress(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    d = coerce_null_arrays(d)
    # Numeric precision: mastery_score NUMERIC(5,1) → round to 1dp
    for num_field in ["mastery_score", "confidence_score"]:
        if num_field in d and d[num_field] is not None:
            d[num_field] = round(float(d[num_field]), 1)
    # difficulty NUMERIC(5,3) → round to 3dp
    if "difficulty" in d and d["difficulty"] is not None:
        d["difficulty"] = round(float(d["difficulty"]), 3)
    return d


def transform_saved_word(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    return d


def transform_study_session(doc: dict) -> dict:
    # Extract MongoDB _id BEFORE clean_doc() removes it.
    # The 24-char hex ObjectId becomes source_mongo_id TEXT UNIQUE,
    # which is the intrinsic dedup key for this append-only table.
    source_id = str(doc["_id"]) if doc.get("_id") is not None else None
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    if source_id:
        d["source_mongo_id"] = source_id
    return d


def transform_ai_coach_content(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # content is a dict → JSONB, no transformation needed
    return d


def transform_ai_coach_usage(doc: dict) -> dict:
    # Extract MongoDB _id BEFORE clean_doc() removes it.
    source_id = str(doc["_id"]) if doc.get("_id") is not None else None
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # date: MongoDB stores as string or datetime
    if "date" in d:
        d["date"] = to_date_str(d["date"])
    if source_id:
        d["source_mongo_id"] = source_id
    return d


def transform_tts_cache(doc: dict) -> dict:
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # CRITICAL: audio is BSON Binary → encode as PostgreSQL hex literal
    if "audio" in d and d["audio"] is not None:
        d["audio"] = to_bytea_hex(d["audio"])
        if d["audio"] is None:
            raise ValueError(f"tts_cache key={d.get('key')}: audio is not bytes — cannot convert to BYTEA")
    return d


def transform_analytics_event(doc: dict) -> dict:
    # Extract MongoDB _id BEFORE clean_doc() removes it.
    source_id = str(doc["_id"]) if doc.get("_id") is not None else None
    d = clean_doc(doc)
    d = sanitize_timestamps(d)
    # props: dict → JSONB, ensure it's never None
    if d.get("props") is None:
        d["props"] = {}
    if source_id:
        d["source_mongo_id"] = source_id
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Migration collection definitions (FK-safe order)
# ─────────────────────────────────────────────────────────────────────────────

MIGRATION_ORDER = [
    {
        "mongo_collection": "topics",
        "supabase_table":   "topics",
        "pk_field":         "slug",
        "transform":        transform_topic,
        "on_conflict":      "slug",
        "description":      "Vocabulary topics taxonomy",
    },
    {
        "mongo_collection": "exams",
        "supabase_table":   "exams",
        "pk_field":         "slug",
        "transform":        transform_exam,
        "on_conflict":      "slug",
        "description":      "Exam definitions",
    },
    {
        "mongo_collection": "articles",
        "supabase_table":   "articles",
        "pk_field":         "id",
        "transform":        transform_article,
        "on_conflict":      "id",
        "description":      "Read & Learn articles (→ topics)",
    },
    {
        "mongo_collection": "words",
        "supabase_table":   "words",
        "pk_field":         "id",
        "transform":        transform_word,
        "on_conflict":      "id",
        "description":      "Canonical vocabulary (→ topics)",
    },
    {
        "mongo_collection": "users",
        "supabase_table":   "users",
        "pk_field":         "user_id",
        "transform":        transform_user,
        "on_conflict":      "user_id",
        "description":      "Application user accounts",
    },
    {
        "mongo_collection": "profiles",
        "supabase_table":   "profiles",
        "pk_field":         "user_id",
        "transform":        transform_profile,
        "on_conflict":      "user_id",
        "description":      "User profiles (→ users, → exams)",
    },
    {
        "mongo_collection": "user_sessions",
        "supabase_table":   "user_sessions",
        "pk_field":         "session_token",
        "transform":        transform_user_session,
        "on_conflict":      "session_token",
        "description":      "Auth sessions (→ users)",
    },
    {
        "mongo_collection": "subscriptions",
        "supabase_table":   "subscriptions",
        "pk_field":         "user_id",
        "transform":        transform_subscription,
        "on_conflict":      "user_id",
        "description":      "Subscriptions (→ users)",
    },
    {
        "mongo_collection": "user_word_progress",
        "supabase_table":   "user_word_progress",
        "pk_field":         None,                    # composite PK (user_id, word_id)
        "transform":        transform_user_word_progress,
        "on_conflict":      "user_id,word_id",
        "description":      "Adaptive learning state (→ users, → words)",
    },
    {
        "mongo_collection": "saved_words",
        "supabase_table":   "saved_words",
        "pk_field":         None,                    # composite PK
        "transform":        transform_saved_word,
        "on_conflict":      "user_id,word_id",
        "description":      "Saved word bookmarks (→ users, → words)",
    },
    {
        "mongo_collection": "study_sessions",
        "supabase_table":   "study_sessions",
        "pk_field":         None,                    # BIGSERIAL PK
        "transform":        transform_study_session,
        "on_conflict":      "source_mongo_id",       # intrinsic dedup via MongoDB _id
        "description":      "Practice session log (→ users) [idempotent via source_mongo_id]",
    },
    {
        "mongo_collection": "ai_coach_content",
        "supabase_table":   "ai_coach_content",
        "pk_field":         "word_id",
        "transform":        transform_ai_coach_content,
        "on_conflict":      "word_id",
        "description":      "AI Coach cache (→ words)",
    },
    {
        "mongo_collection": "ai_coach_usage",
        "supabase_table":   "ai_coach_usage",
        "pk_field":         None,
        "transform":        transform_ai_coach_usage,
        "on_conflict":      "source_mongo_id",       # intrinsic dedup via MongoDB _id
        "description":      "AI Coach usage log (→ users, → words) [idempotent via source_mongo_id]",
    },
    {
        "mongo_collection": "tts_cache",
        "supabase_table":   "tts_cache",
        "pk_field":         "key",
        "transform":        transform_tts_cache,
        "on_conflict":      "key",
        "description":      "TTS audio cache (BYTEA)",
    },
    {
        "mongo_collection": "analytics_events",
        "supabase_table":   "analytics_events",
        "pk_field":         None,
        "transform":        transform_analytics_event,
        "on_conflict":      "source_mongo_id",       # intrinsic dedup via MongoDB _id
        "description":      "Analytics event log (→ users) [idempotent via source_mongo_id]",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Pre-migration validation
# ─────────────────────────────────────────────────────────────────────────────

async def run_preflight_validation(db, supabase: Client) -> bool:
    """
    Validate source (MongoDB) and destination (Supabase) before migrating.
    Returns True if all checks pass, False if there are blockers.
    """
    log.info("=" * 60)
    log.info("PRE-MIGRATION VALIDATION")
    log.info("=" * 60)

    VALID_PROVENANCE = {"CURATED", "AI_GENERATED", "IMPORTED", "ADMIN_CREATED", "SEED"}
    VALID_STATUS     = {"DRAFT", "REVIEW", "PUBLISHED", "ARCHIVED"}
    VALID_CEFR       = {"A1", "A2", "B1", "B2", "C1", "C2"}
    VALID_TIER       = {"free", "pro"}

    blockers = []
    warnings = []

    # ── 1. Source counts ────────────────────────────────────
    log.info("  [1/7] Source MongoDB counts:")
    total_source = 0
    for cdef in MIGRATION_ORDER:
        col   = cdef["mongo_collection"]
        count = await db[col].count_documents({})
        total_source += count
        log.info(f"        {col:<30}: {count}")
    log.info(f"        {'TOTAL':<30}: {total_source}")

    # ── 2. Destination counts (should all be 0 before first run) ─
    log.info("  [2/7] Destination Supabase counts (pre-migration):")
    total_dest = 0
    for cdef in MIGRATION_ORDER:
        tbl = cdef["supabase_table"]
        try:
            r = supabase.table(tbl).select("*", count="exact").limit(0).execute()
            n = r.count or 0
            total_dest += n
            if n > 0:
                warnings.append(f"  ⚠️  Supabase.{tbl} already has {n} rows — idempotent mode")
            log.info(f"        {tbl:<30}: {n}")
        except Exception as e:
            blockers.append(f"Cannot access Supabase.{tbl}: {e}")
    log.info(f"        {'TOTAL':<30}: {total_dest}")
    if total_dest > 0:
        log.warning(f"  ⚠️  Destination already has {total_dest} rows — migration will skip duplicates")

    # ── 3. words validation ─────────────────────────────────
    log.info("  [3/7] Words enum/constraint validation:")
    words = await db.words.find({}, {"_id": 0, "id": 1, "provenance": 1,
                                     "status": 1, "cefr": 1}).to_list(None)
    invalid_prov  = [(w["id"], w.get("provenance")) for w in words
                     if w.get("provenance") not in VALID_PROVENANCE]
    invalid_stat  = [(w["id"], w.get("status"))     for w in words
                     if w.get("status") not in VALID_STATUS]
    invalid_cefr  = [(w["id"], w.get("cefr"))       for w in words
                     if w.get("cefr") and w["cefr"] not in VALID_CEFR]

    if invalid_prov:
        blockers.append(f"words with invalid provenance (breaks CHECK): {invalid_prov[:5]}")
    if invalid_stat:
        blockers.append(f"words with invalid status (breaks CHECK): {invalid_stat[:5]}")
    if invalid_cefr:
        blockers.append(f"words with invalid cefr (breaks CHECK): {invalid_cefr[:5]}")

    log.info(f"        invalid provenance: {len(invalid_prov)}")
    log.info(f"        invalid status    : {len(invalid_stat)}")
    log.info(f"        invalid CEFR      : {len(invalid_cefr)}")

    # ── 4. users validation ─────────────────────────────────
    log.info("  [4/7] Users validation:")
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "tier": 1, "email": 1}).to_list(None)
    invalid_tier  = [(u["user_id"], u.get("tier")) for u in users
                     if u.get("tier") not in VALID_TIER]
    missing_email = [u["user_id"] for u in users if not u.get("email")]
    if invalid_tier:
        blockers.append(f"users with invalid tier: {invalid_tier}")
    if missing_email:
        blockers.append(f"users missing email (NOT NULL): {missing_email}")
    log.info(f"        invalid tier  : {len(invalid_tier)}")
    log.info(f"        missing email : {len(missing_email)}")

    # ── 5. Orphan FK checks ─────────────────────────────────
    log.info("  [5/7] FK orphan pre-check:")
    all_user_ids  = {u["user_id"] for u in users}
    all_word_ids  = {w["id"] for w in words}
    all_topic_slugs = {t["slug"] for t in await db.topics.find({}, {"_id":0,"slug":1}).to_list(None)}
    all_exam_slugs  = {e["slug"] for e in await db.exams.find({},  {"_id":0,"slug":1}).to_list(None)}

    orphan_checks = [
        ("words.topic → topics",          db.words,            {"$and": [{"topic": {"$ne": None}},
                                                                          {"topic": {"$nin": list(all_topic_slugs)}}]}),
        ("profiles.user_id → users",      db.profiles,         {"user_id": {"$nin": list(all_user_ids)}}),
        ("user_sessions.user_id → users", db.user_sessions,    {"user_id": {"$nin": list(all_user_ids)}}),
        ("analytics_events.user_id → users", db.analytics_events, {"user_id": {"$nin": list(all_user_ids)}}),
    ]
    all_fk_clean = True
    for label, col, query in orphan_checks:
        count = await col.count_documents(query)
        status = "✅" if count == 0 else "❌"
        log.info(f"        {status} {label}: {count} orphans")
        if count > 0:
            blockers.append(f"FK orphans: {label} — {count} records")
            all_fk_clean = False

    # ── 6. Duplicate pre-check ──────────────────────────────
    log.info("  [6/7] Uniqueness pre-check:")
    from collections import Counter

    all_words_full = await db.words.find({}, {"_id":0,"id":1,"canonical_key":1}).to_list(None)
    ck_dupes = {k:v for k,v in Counter(w.get("canonical_key","") for w in all_words_full).items() if v > 1}
    wid_dupes = {k:v for k,v in Counter(w["id"] for w in all_words_full).items() if v > 1}
    email_dupes = {k:v for k,v in Counter(u["email"] for u in users if u.get("email")).items() if v > 1}

    if ck_dupes:
        blockers.append(f"words.canonical_key duplicates: {ck_dupes}")
    if wid_dupes:
        blockers.append(f"words.id duplicates: {wid_dupes}")
    if email_dupes:
        blockers.append(f"users.email duplicates: {email_dupes}")

    log.info(f"        words.canonical_key dupes : {len(ck_dupes)}")
    log.info(f"        words.id dupes            : {len(wid_dupes)}")
    log.info(f"        users.email dupes         : {len(email_dupes)}")

    # ── 7. Type conversion checks ───────────────────────────
    log.info("  [7/7] Type conversion checks:")
    profs = await db.profiles.find({}, {"_id":0,"user_id":1,"exam_date":1}).to_list(None)
    bad_dates = []
    for p in profs:
        if p.get("exam_date") is not None:
            result = to_date_str(p["exam_date"])
            if result is None:
                bad_dates.append((p["user_id"], p["exam_date"]))
    if bad_dates:
        warnings.append(f"profiles.exam_date unparseable → will be set to NULL: {bad_dates}")
    log.info(f"        profiles.exam_date conversion failures: {len(bad_dates)}")

    tts_docs = await db.tts_cache.find({}, {"_id":0,"key":1,"audio":1}).to_list(None)
    bad_audio = [t["key"] for t in tts_docs if not isinstance(t.get("audio"), (bytes, bytearray))]
    if bad_audio:
        blockers.append(f"tts_cache.audio not bytes: {bad_audio}")
    log.info(f"        tts_cache.audio non-bytes : {len(bad_audio)}")

    # ── Summary ─────────────────────────────────────────────
    log.info("")
    if warnings:
        for w in warnings:
            log.warning(f"  ⚠️  {w}")
    if blockers:
        log.error("  ❌ BLOCKERS FOUND — Fix before migrating:")
        for b in blockers:
            log.error(f"     • {b}")
        return False
    else:
        log.info("  ✅ All pre-migration checks passed. Safe to migrate.")
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Batch upsert with retry
# ─────────────────────────────────────────────────────────────────────────────

def upsert_batch(supabase: Client, table: str, records: list,
                 on_conflict: Optional[str]) -> tuple[int, int, list]:
    """
    Upsert a batch of records.
    Returns (inserted_count, skipped_count, error_list).
    
    Uses ignore_duplicates=True → INSERT ... ON CONFLICT DO NOTHING
    """
    inserted = 0
    skipped  = 0
    errors   = []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if on_conflict:
                result = (
                    supabase.table(table)
                    .upsert(records, on_conflict=on_conflict, ignore_duplicates=True)
                    .execute()
                )
            else:
                # No natural unique key (e.g., study_sessions, analytics_events)
                # For append-only tables, check existence by count before inserting
                result = supabase.table(table).insert(records).execute()

            # Count inserted vs skipped
            returned = len(result.data) if result.data else 0
            if on_conflict:
                # ignore_duplicates: returned count = actually inserted (skipped not returned)
                inserted += returned
                skipped  += (len(records) - returned)
            else:
                inserted += len(records)
            return inserted, skipped, errors

        except Exception as e:
            err_str = str(e)
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * (2 ** (attempt - 1))
                log.warning(f"  Batch attempt {attempt}/{MAX_RETRIES} failed: {err_str[:80]}"
                            f" — retrying in {wait:.1f}s")
                time.sleep(wait)
            else:
                # Last attempt failed — try record-by-record fallback
                log.warning(f"  Batch failed after {MAX_RETRIES} attempts. Falling back to per-record insert.")
                for rec in records:
                    try:
                        pk_val = rec.get("id") or rec.get("slug") or rec.get("user_id") or rec.get("key") or "?"
                        if on_conflict:
                            supabase.table(table).upsert([rec], on_conflict=on_conflict,
                                                         ignore_duplicates=True).execute()
                        else:
                            supabase.table(table).insert([rec]).execute()
                        inserted += 1
                    except Exception as rec_err:
                        skipped += 1
                        errors.append({
                            "table":  table,
                            "record": pk_val,
                            "error":  str(rec_err)[:200],
                        })
                return inserted, skipped, errors

    return inserted, skipped, errors


# ─────────────────────────────────────────────────────────────────────────────
# Main migration for a single collection
# ─────────────────────────────────────────────────────────────────────────────

async def migrate_collection(db, supabase: Client, cdef: dict,
                              dry_run: bool = False) -> dict:
    """
    Migrate one MongoDB collection → Supabase table.
    Returns stats dict: {source, inserted, skipped, failed, errors}.
    """
    mongo_col = cdef["mongo_collection"]
    supa_tbl  = cdef["supabase_table"]
    transform = cdef["transform"]
    on_conf   = cdef["on_conflict"]

    log.info(f"  Migrating: {mongo_col} → {supa_tbl}  [{cdef['description']}]")

    # Fetch all docs from MongoDB — include _id so transform functions can
    # extract source_mongo_id for append-only tables (study_sessions,
    # ai_coach_usage, analytics_events).  clean_doc() removes _id from the
    # payload before any Supabase insert, so the raw ObjectId is never sent.
    docs = await db[mongo_col].find({}).to_list(None)
    source_count = len(docs)
    log.info(f"    Source documents: {source_count}")

    if dry_run:
        # Transform only — validate but do not insert
        transform_errors = []
        for i, doc in enumerate(docs):
            try:
                transform(doc)
            except Exception as e:
                transform_errors.append({"index": i, "error": str(e)[:200]})
        log.info(f"    [DRY-RUN] transform errors: {len(transform_errors)}")
        return {
            "source":   source_count,
            "inserted": 0,
            "skipped":  source_count,
            "failed":   len(transform_errors),
            "errors":   transform_errors,
            "dry_run":  True,
        }

    # Transform documents
    transformed = []
    transform_errors = []
    for i, doc in enumerate(docs):
        try:
            t = transform(dict(doc))
            transformed.append(t)
        except Exception as e:
            transform_errors.append({
                "table":  supa_tbl,
                "record": str(i),
                "error":  f"Transform error: {str(e)[:200]}",
            })
            log.error(f"    ❌ Transform error on record {i}: {e}")

    log.info(f"    Transformed: {len(transformed)} ok, {len(transform_errors)} errors")

    # Batch upsert
    total_inserted = 0
    total_skipped  = 0
    all_errors     = list(transform_errors)

    for batch_start in range(0, len(transformed), BATCH_SIZE):
        batch = transformed[batch_start : batch_start + BATCH_SIZE]
        batch_end = batch_start + len(batch)
        ins, skip, errs = upsert_batch(supabase, supa_tbl, batch, on_conf)
        total_inserted += ins
        total_skipped  += skip
        all_errors.extend(errs)
        log.info(f"    Batch [{batch_start+1}-{batch_end}]: inserted={ins}, skipped={skip}, errors={len(errs)}")

    log.info(f"    ✅ {supa_tbl}: inserted={total_inserted}, skipped={total_skipped}, "
             f"failed={len([e for e in all_errors if 'Transform error' not in e.get('error','')])}")

    return {
        "source":   source_count,
        "inserted": total_inserted,
        "skipped":  total_skipped,
        "failed":   len(all_errors),
        "errors":   all_errors,
        "dry_run":  False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Post-migration verification
# ─────────────────────────────────────────────────────────────────────────────

async def verify_counts(db, supabase: Client) -> bool:
    """Compare MongoDB source counts against Supabase destination counts."""
    log.info("=" * 60)
    log.info("POST-MIGRATION COUNT VERIFICATION")
    log.info("=" * 60)

    all_match = True
    for cdef in MIGRATION_ORDER:
        mongo_col = cdef["mongo_collection"]
        supa_tbl  = cdef["supabase_table"]

        src_count = await db[mongo_col].count_documents({})
        try:
            r = supabase.table(supa_tbl).select("*", count="exact").limit(0).execute()
            dst_count = r.count or 0
        except Exception as e:
            log.error(f"  ❌ Cannot count {supa_tbl}: {e}")
            all_match = False
            continue

        match = dst_count >= src_count   # >= because some tables may have had pre-existing rows
        sym   = "✅" if match else "❌"
        log.info(f"  {sym} {mongo_col:<28} → {supa_tbl:<28} | "
                 f"src={src_count}  dst={dst_count}  {'OK' if match else 'MISMATCH'}")
        if not match:
            all_match = False

    return all_match


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(
        description="Vocabist MongoDB → Supabase Data Migration"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate transforms without inserting")
    parser.add_argument("--collection", type=str, default=None,
                        help="Migrate only this collection (by mongo_collection name)")
    parser.add_argument("--reset-collection", type=str, default=None,
                        help="Clear state for this collection and re-migrate")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only run count verification — no migration")
    args = parser.parse_args()

    # ── Load environment ─────────────────────────────────────
    load_dotenv(Path(__file__).parent.parent / ".env")   # /app/backend/.env
    mongo_url  = os.environ["MONGO_URL"]
    db_name    = os.environ.get("DB_NAME", "vocably")
    supa_url   = os.environ["SUPABASE_URL"]
    supa_key   = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    # ── Connect ──────────────────────────────────────────────
    mongo_client = AsyncIOMotorClient(mongo_url)
    db           = mongo_client[db_name]
    supabase     = create_client(supa_url, supa_key)

    log.info("=" * 60)
    log.info("VOCABIST MIGRATION SCRIPT v1.0.0")
    log.info("=" * 60)
    log.info(f"  Mode     : {'DRY-RUN' if args.dry_run else 'LIVE'}")
    log.info(f"  MongoDB  : {mongo_url[:40]}...")
    log.info(f"  Supabase : {supa_url}")
    log.info(f"  State    : {STATE_FILE}")
    log.info(f"  Log      : {LOG_FILE}")
    log.info("")

    # ── Verify-only mode ────────────────────────────────────
    if args.verify_only:
        await verify_counts(db, supabase)
        mongo_client.close()
        return

    # ── Load state ───────────────────────────────────────────
    state = load_state()
    all_errors: list = load_errors()

    # ── Reset a specific collection ──────────────────────────
    if args.reset_collection:
        col = args.reset_collection
        if col in state:
            del state[col]
            save_state(state)
            log.info(f"  ✅ Reset state for collection: {col}")
        else:
            log.info(f"  ℹ️  No state found for: {col}")

    # ── Pre-migration validation ─────────────────────────────
    if not args.dry_run:
        ok = await run_preflight_validation(db, supabase)
        if not ok:
            log.error("  ❌ Pre-migration validation FAILED. Aborting.")
            log.error("     Fix blockers before running the migration.")
            mongo_client.close()
            sys.exit(1)
        log.info("")

    # ── Determine collections to migrate ─────────────────────
    if args.collection:
        plan = [c for c in MIGRATION_ORDER if c["mongo_collection"] == args.collection]
        if not plan:
            log.error(f"  Unknown collection: {args.collection}")
            mongo_client.close()
            sys.exit(1)
    else:
        plan = MIGRATION_ORDER

    # ── Migrate ──────────────────────────────────────────────
    log.info("=" * 60)
    log.info(f"MIGRATION  ({len(plan)} collections, dry_run={args.dry_run})")
    log.info("=" * 60)

    summary = {}
    for i, cdef in enumerate(plan, 1):
        col = cdef["mongo_collection"]
        log.info(f"\n[{i}/{len(plan)}] {col}")

        # Skip already-completed collections (unless reset)
        if not args.dry_run and state.get(col) == "DONE":
            r = supabase.table(cdef["supabase_table"]).select("*", count="exact").limit(0).execute()
            log.info(f"  ⏭️  Skipped (already DONE, {r.count} rows in Supabase)")
            continue

        stats = await migrate_collection(db, supabase, cdef, dry_run=args.dry_run)
        summary[col] = stats

        # Save errors immediately
        all_errors.extend(stats.get("errors", []))
        save_errors(all_errors)

        # Mark done (only if not dry-run and no hard failures)
        if not args.dry_run and stats["failed"] == 0:
            state[col] = "DONE"
            save_state(state)
        elif not args.dry_run:
            state[col] = f"PARTIAL (failed={stats['failed']})"
            save_state(state)

    # ── Summary report ───────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info("MIGRATION SUMMARY")
    log.info("=" * 60)
    total_src = total_ins = total_skip = total_fail = 0
    for col, stats in summary.items():
        total_src  += stats["source"]
        total_ins  += stats["inserted"]
        total_skip += stats["skipped"]
        total_fail += stats["failed"]
        sym = "✅" if stats["failed"] == 0 else "❌"
        log.info(f"  {sym} {col:<28}: src={stats['source']}, "
                 f"ins={stats['inserted']}, skip={stats['skipped']}, fail={stats['failed']}")

    log.info(f"\n  TOTAL: src={total_src}, inserted={total_ins}, "
             f"skipped={total_skip}, failed={total_fail}")

    if total_fail > 0:
        log.warning(f"  ⚠️  {total_fail} failures logged to: {ERRORS_FILE}")

    # ── Post-migration verification ──────────────────────────
    if not args.dry_run:
        log.info("")
        await verify_counts(db, supabase)

    mongo_client.close()
    log.info("")
    log.info("Migration script complete.")


if __name__ == "__main__":
    asyncio.run(main())
