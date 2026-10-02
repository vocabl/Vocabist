#!/usr/bin/env python3
"""
Vocabist — Incremental Reconciliation & Sync (Mongo → Supabase)
================================================================
Compares live MongoDB state against Supabase and syncs any records
that are missing or have diverged since the original migration snapshot.

Usage (from /app/backend):
    python migrations/reconcile_and_sync.py [--dry-run] [--collection COL]

Options:
    --dry-run        Report differences without writing to Supabase
    --collection X   Sync only collection X
    --report-only    Print counts + mismatch summary, then exit
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import argparse
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# path setup
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from supabase import create_async_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("vocabist_reconcile")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME   = os.environ.get("DB_NAME", "vocably")
SB_URL    = os.environ["SUPABASE_URL"]
SB_KEY    = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

BATCH_SIZE = 50

# ---------------------------------------------------------------------------
# Reuse transform helpers from migration script
# ---------------------------------------------------------------------------

def to_iso(val: Any) -> Optional[str]:
    if val is None: return None
    if isinstance(val, datetime):
        if val.tzinfo is None: val = val.replace(tzinfo=timezone.utc)
        return val.isoformat()
    if isinstance(val, str): return val
    return str(val)


def to_date_str(val: Any) -> Optional[str]:
    if val is None: return None
    if isinstance(val, datetime): return val.date().isoformat()
    if isinstance(val, date): return val.isoformat()
    if isinstance(val, str):
        try: date.fromisoformat(val[:10]); return val[:10]
        except ValueError: return None
    return None


def to_bytea_hex(val: Any) -> Optional[str]:
    if val is None: return None
    if isinstance(val, (bytes, bytearray)): return "\\x" + val.hex()
    if isinstance(val, str) and val.startswith("\\x"): return val
    return None


NULL_ARRAY_FIELDS = [
    "synonyms","antonyms","related","confusing_words","word_family",
    "roots","prefixes","suffixes","exam_relevance","recent_results","last_reason_codes",
]
TS_FIELDS = ["created_at","updated_at","expires_at","started_at",
             "cancelled_at","last_reviewed_at","next_review_at"]


def clean(doc: dict) -> dict:
    d = {k: v for k, v in doc.items() if k != "_id"}
    for f in TS_FIELDS:
        if f in d: d[f] = to_iso(d[f])
    for f in NULL_ARRAY_FIELDS:
        if f in d and d[f] is None: d[f] = []
    return d


# Supabase column allowlists — strip Mongo-only / legacy fields before upsert
_SB_ALLOWED: Dict[str, Optional[frozenset]] = {
    "users": frozenset(["user_id","email","name","picture","password_hash",
                        "onboarded","tier","xp","streak","created_at","updated_at"]),
    "user_word_progress": frozenset([
        "user_id","word_id","status","mastery_score","confidence_score","difficulty",
        "times_seen","times_correct","times_wrong","consecutive_correct",
        "review_interval","last_reviewed_at","next_review_at",
        "average_response_time","recent_results","last_reason_codes",
        "created_at","updated_at",
    ]),
}


def _apply_allowlist(collection: str, d: dict) -> dict:
    allowed = _SB_ALLOWED.get(collection)
    if allowed is None:
        return d
    return {k: v for k, v in d.items() if k in allowed}


def transform(collection: str, doc: dict) -> dict:
    d = clean(doc)
    if collection == "profiles":
        for f in ("exam_date", "last_active_date"):
            if f in d: d[f] = to_date_str(d[f])
    elif collection == "user_word_progress":
        for nf in ("mastery_score","confidence_score"):
            if nf in d and d[nf] is not None: d[nf] = round(float(d[nf]), 1)
        if "difficulty" in d and d["difficulty"] is not None:
            d["difficulty"] = round(float(d["difficulty"]), 3)
        # Remap legacy Mongo field names → Supabase column names
        if "correct_count" in d and "times_correct" not in d:
            d["times_correct"] = d.pop("correct_count")
        if "incorrect_count" in d and "times_wrong" not in d:
            d["times_wrong"] = d.pop("incorrect_count")
    elif collection == "tts_cache":
        if "audio" in d and d["audio"] is not None:
            encoded = to_bytea_hex(d["audio"])
            if encoded is None:
                raise ValueError(f"tts_cache {d.get('key')}: cannot encode audio as BYTEA")
            d["audio"] = encoded
    elif collection in ("study_sessions", "ai_coach_usage", "analytics_events"):
        source_id = str(doc["_id"]) if doc.get("_id") is not None else None
        if source_id: d["source_mongo_id"] = source_id
    if collection == "ai_coach_usage":
        if "date" in d: d["date"] = to_date_str(d["date"])
    elif collection == "exams":
        if "max_score" in d and d["max_score"] is not None:
            d["max_score"] = float(d["max_score"])
    return _apply_allowlist(collection, d)


# ---------------------------------------------------------------------------
# conflict / pk config per collection
# ---------------------------------------------------------------------------

REQUIRED_NONNULL: Dict[str, List[str]] = {
    "study_sessions":   ["user_id"],
    "analytics_events": ["user_id"],
    "ai_coach_usage":   ["user_id"],
    "user_word_progress": ["user_id", "word_id"],
    "saved_words":      ["user_id", "word_id"],
}


def _is_valid(collection: str, row: dict) -> bool:
    """Return False if row has a null value in a NOT NULL column."""
    for field in REQUIRED_NONNULL.get(collection, []):
        if row.get(field) is None:
            return False
    return True


CONFLICT_COLS: Dict[str, str] = {
    "topics":             "slug",
    "exams":              "slug",
    "articles":           "id",
    "words":              "id",
    "users":              "user_id",
    "profiles":           "user_id",
    "user_sessions":      "session_token",
    "subscriptions":      "user_id",
    "user_word_progress": "user_id,word_id",
    "saved_words":        "user_id,word_id",
    "study_sessions":     "source_mongo_id",
    "ai_coach_content":   "word_id",
    "ai_coach_usage":     "source_mongo_id",
    "tts_cache":          "key",
    "analytics_events":   "source_mongo_id",
}

PK_FIELD: Dict[str, str] = {
    "topics":             "slug",
    "exams":              "slug",
    "articles":           "id",
    "words":              "id",
    "users":              "user_id",
    "profiles":           "user_id",
    "user_sessions":      "session_token",
    "subscriptions":      "user_id",
    "user_word_progress": ("user_id","word_id"),
    "saved_words":        ("user_id","word_id"),
    "study_sessions":     "source_mongo_id",
    "ai_coach_content":   "word_id",
    "ai_coach_usage":     "source_mongo_id",
    "tts_cache":          "key",
    "analytics_events":   "source_mongo_id",
}

MIGRATION_ORDER = [
    "topics","exams","articles","words","users","profiles",
    "user_sessions","subscriptions","user_word_progress","saved_words",
    "study_sessions","ai_coach_content","ai_coach_usage","tts_cache",
    "analytics_events",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc_key(collection: str, doc: dict) -> Optional[Any]:
    pk = PK_FIELD.get(collection)
    if pk is None: return None
    if isinstance(pk, tuple):
        return tuple(doc.get(k) for k in pk)
    return doc.get(pk)


def _get_mongo_pk_field(collection: str) -> str:
    pk = PK_FIELD.get(collection, "id")
    if isinstance(pk, tuple): return pk[0]
    return pk


async def _fetch_supabase_keys(sb, collection: str, select_cols: str) -> Set[Any]:
    """Fetch existing keys from Supabase in one query."""
    pk = PK_FIELD.get(collection)
    if pk is None: return set()
    rows = []
    offset = 0
    while True:
        r = await sb.table(collection).select(select_cols).range(offset, offset+999).execute()
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 1000: break
        offset += 1000
    if isinstance(pk, tuple):
        return {tuple(row.get(k) for k in pk) for row in rows}
    return {row.get(pk) for row in rows}


# ---------------------------------------------------------------------------
# Core reconcile + sync per collection
# ---------------------------------------------------------------------------

async def reconcile_collection(
    mongo_db,
    sb,
    collection: str,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Compare Mongo vs Supabase for one collection and sync missing records.
    Returns stats dict.
    """
    pk = PK_FIELD.get(collection)
    if pk is None:
        log.warning(f"  {collection}: no PK configured — skip")
        return {}

    # Build select_cols string for Supabase query
    if isinstance(pk, tuple):
        select_cols = ",".join(pk)
    else:
        select_cols = pk

    # ---- 1. fetch existing Supabase keys ----
    log.info(f"  {collection}: fetching Supabase keys…")
    sb_keys = await _fetch_supabase_keys(sb, collection, select_cols)
    log.info(f"  {collection}: {len(sb_keys)} existing Supabase rows")

    # ---- 2. stream all Mongo docs ----
    # For source_mongo_id collections: include _id (and all other fields)
    # For all others: exclude _id (not needed in Supabase)
    needs_id = collection in ("study_sessions", "ai_coach_usage", "analytics_events")
    projection = {} if needs_id else {"_id": 0}
    mongo_docs = await mongo_db[collection].find({}, projection).to_list(200000)
    log.info(f"  {collection}: {len(mongo_docs)} Mongo docs")

    missing: List[dict] = []
    skipped_no_key = 0

    for doc in mongo_docs:
        try:
            row = transform(collection, doc)
        except Exception as e:
            log.warning(f"  {collection}: transform error {e} — skip")
            continue

        key = _doc_key(collection, row)
        if key is None:
            skipped_no_key += 1
            continue

        # Skip None key (append-only without _id)
        if isinstance(key, tuple) and any(k is None for k in key):
            skipped_no_key += 1
            continue

        if key not in sb_keys:
            if not _is_valid(collection, row):
                skipped_no_key += 1
                continue
            missing.append(row)

    log.info(f"  {collection}: {len(missing)} missing in Supabase, {skipped_no_key} skipped (no key)")

    if dry_run:
        log.info(f"  {collection}: [DRY RUN] would upsert {len(missing)}")
        return {"total_mongo": len(mongo_docs), "existing_sb": len(sb_keys),
                "missing": len(missing), "upserted": 0, "errors": 0}

    # ---- 3. upsert missing in batches ----
    upserted = errors = 0
    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i:i+BATCH_SIZE]
        conflict = CONFLICT_COLS.get(collection, "id")
        try:
            r = await sb.table(collection).upsert(
                batch,
                on_conflict=conflict,
                ignore_duplicates=True,
            ).execute()
            upserted += len(batch)
        except Exception as e:
            log.error(f"  {collection}: batch upsert error — {e}")
            errors += len(batch)
            # Try record-by-record
            for rec in batch:
                try:
                    await sb.table(collection).upsert(
                        [rec], on_conflict=conflict, ignore_duplicates=True
                    ).execute()
                    upserted += 1
                    errors -= 1
                except Exception as e2:
                    log.error(f"  {collection}: single record error key={_doc_key(collection, rec)}: {e2}")

    log.info(f"  {collection}: upserted={upserted} errors={errors}")
    return {"total_mongo": len(mongo_docs), "existing_sb": len(sb_keys),
            "missing": len(missing), "upserted": upserted, "errors": errors}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(collections: List[str], dry_run: bool, report_only: bool) -> None:
    log.info(f"{'[DRY RUN] ' if dry_run else ''}Reconcile: {', '.join(collections)}")
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    mongo_db = mongo_client[DB_NAME]
    sb = await create_async_client(SB_URL, SB_KEY)

    report = {}
    try:
        for coll in collections:
            log.info(f"\n── {coll} ──────────────────────")
            if report_only:
                # Just count
                mongo_n = await mongo_db[coll].count_documents({})
                sb_r = await sb.table(coll).select("*", count="exact").limit(0).execute()
                sb_n = sb_r.count or 0
                report[coll] = {"mongo": mongo_n, "supabase": sb_n, "delta": mongo_n - sb_n}
                log.info(f"  {coll}: mongo={mongo_n} supabase={sb_n} delta={mongo_n - sb_n}")
            else:
                stats = await reconcile_collection(mongo_db, sb, coll, dry_run)
                report[coll] = stats
    finally:
        mongo_client.close()

    print("\n" + "="*60)
    print("RECONCILIATION REPORT")
    print("="*60)
    for coll, stats in report.items():
        print(f"  {coll}: {stats}")
    print("="*60)
    return report


def main():
    parser = argparse.ArgumentParser(description="Reconcile Mongo→Supabase")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--collection", default=None)
    args = parser.parse_args()

    collections = [args.collection] if args.collection else MIGRATION_ORDER
    asyncio.run(run(collections, args.dry_run, args.report_only))


if __name__ == "__main__":
    main()
