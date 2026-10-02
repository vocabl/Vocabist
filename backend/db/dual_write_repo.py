"""
DualWriteRepository
===================
Mongo-authoritative + Supabase mirror during the 72-hour validation period.

Design:
  - ALL reads -> MongoRepository
  - ALL writes -> MongoRepository first (authoritative)
  - On Mongo success -> mirror write to SupabaseRepository (best-effort)
  - On Supabase mirror failure -> record in dual_write_outbox (MongoDB)
  - On Mongo failure -> raise exception; Supabase is NOT written
  - __getattr__ delegates any unimplemented method to Mongo transparently

OUTBOX (dual_write_outbox in MongoDB):
  op_id        sha256 of (collection, pk_value, payload)
  collection   Supabase table name
  operation    upsert | delete
  pk_field     conflict column(s)
  pk_value     serialised primary key
  payload      row dict to replay
  user_id      context (may be None)
  error        last Supabase error
  retry_count  attempts so far
  resolved     True once replayed successfully
  created_at   ISO timestamp
  resolved_at  ISO timestamp (or None)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from db.base import DatabaseRepository
from db.mongo_repo import MongoRepository
from db.supabase_repo import SupabaseRepository

log = logging.getLogger("vocabist.dual_write")

# ---------------------------------------------------------------------------
# Supabase table column allowlists — filter Mongo payloads before mirroring
# ---------------------------------------------------------------------------
_SB_COLS: Dict[str, frozenset] = {
    "users": frozenset(["user_id","email","name","picture","password_hash",
                        "onboarded","tier","xp","streak","created_at","updated_at"]),
    "profiles": frozenset(["user_id","reason","level","daily_minutes","exam_slug",
                            "exam_date","target_score","streak","longest_streak",
                            "xp","last_active_date","created_at","updated_at"]),
    "user_sessions": frozenset(["session_token","user_id","created_at","expires_at"]),
    "subscriptions": frozenset(["user_id","plan","status","platform",
                                 "started_at","cancelled_at","updated_at"]),
    "saved_words": frozenset(["user_id","word_id","created_at"]),
    "tts_cache": frozenset(["key","audio","created_at"]),
    "ai_coach_content": frozenset(["word_id","content","provenance","status","created_at"]),
    "analytics_events": frozenset(["user_id","event","props","created_at","source_mongo_id"]),
    "study_sessions": frozenset(["user_id","answered","correct","duration_ms",
                                  "source","created_at","source_mongo_id"]),
    "ai_coach_usage": frozenset(["user_id","word_id","date","created_at","source_mongo_id"]),
}


def _filter(collection: str, payload: dict) -> dict:
    """Keep only columns that exist in the Supabase schema."""
    allowed = _SB_COLS.get(collection)
    if allowed is None:
        return {k: v for k, v in payload.items() if k != "_id"}
    return {k: v for k, v in payload.items() if k in allowed}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _op_id(collection: str, pk_value: Any, payload: dict) -> str:
    raw = f"{collection}:{pk_value}:{json.dumps(payload, sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class DualWriteRepository:  # intentionally NOT inheriting DatabaseRepository
    """                      # so __getattr__ can delegate reads to Mongo cleanly
    Write-to-both repository.  Reads are always served from MongoDB.
    (Duck-typing: implements the same interface without inheriting to allow
     __getattr__ delegation for all unimplemented read methods.)
    """

    def __init__(self) -> None:
        self._mongo = MongoRepository()
        self._supabase = SupabaseRepository()

    # ------------------------------------------------------------------
    # Transparent delegation for all unimplemented methods -> Mongo
    # ------------------------------------------------------------------
    def __getattr__(self, name: str):
        """Delegate any method not explicitly defined here to MongoRepository."""
        attr = getattr(self._mongo, name)
        return attr

    # ------------------------------------------------------------------
    # Mirror helper
    # ------------------------------------------------------------------
    async def _mirror_upsert(
        self,
        collection: str,
        conflict: str,
        payload: dict,
        pk_value: Any = None,
        user_id: Optional[str] = None,
    ) -> None:
        if pk_value is None:
            pk_value = json.dumps(
                {k: payload.get(k) for k in conflict.split(",")}, default=str
            )
        oid = _op_id(collection, pk_value, payload)
        try:
            sb = await self._supabase._client()
            await sb.table(collection).upsert(
                [payload], on_conflict=conflict, ignore_duplicates=False
            ).execute()
        except Exception as e:
            log.warning(
                f"[dw] mirror upsert failed {collection}/{pk_value}: {e} — outbox"
            )
            await self._record_outbox(
                oid, collection, "upsert", conflict, pk_value, payload, user_id, str(e)
            )

    async def _mirror_delete(
        self,
        collection: str,
        pk_field: str,
        pk_value: str,
        user_id: Optional[str] = None,
    ) -> None:
        try:
            sb = await self._supabase._client()
            q = sb.table(collection).delete()
            for f, v in zip(pk_field.split(","), str(pk_value).split(":")):
                q = q.eq(f.strip(), v)
            await q.execute()
        except Exception as e:
            log.warning(f"[dw] mirror delete failed {collection}/{pk_value}: {e}")

    async def _record_outbox(
        self,
        op_id: str,
        collection: str,
        operation: str,
        pk_field: str,
        pk_value: Any,
        payload: dict,
        user_id: Optional[str],
        error: str,
    ) -> None:
        try:
            db = self._mongo._db
            await db.dual_write_outbox.update_one(
                {"op_id": op_id},
                {"$setOnInsert": {
                    "op_id": op_id, "collection": collection, "operation": operation,
                    "pk_field": pk_field, "pk_value": str(pk_value),
                    "payload": payload, "user_id": user_id, "error": error,
                    "retry_count": 0, "resolved": False,
                    "created_at": _now(), "resolved_at": None,
                }},
                upsert=True,
            )
        except Exception as oe:
            log.error(f"[dw] CRITICAL: outbox write failed: {oe}")

    # ------------------------------------------------------------------
    # WRITE overrides  (Mongo authoritative + Supabase mirror)
    # ------------------------------------------------------------------

    # Auth / sessions
    async def create_session(self, doc: Dict[str, Any]) -> None:
        await self._mongo.create_session(doc)
        payload = _filter("user_sessions", doc)
        if hasattr(payload.get("expires_at"), "isoformat"):
            payload["expires_at"] = payload["expires_at"].isoformat()
        await self._mirror_upsert("user_sessions", "session_token",
                                   payload, payload.get("session_token"),
                                   payload.get("user_id"))

    async def delete_session(self, token: str) -> None:
        await self._mongo.delete_session(token)
        await self._mirror_delete("user_sessions", "session_token", token)

    async def delete_expired_sessions(self) -> None:
        await self._mongo.delete_expired_sessions()
        # Supabase pg_cron handles its own purge; no mirror needed here

    # Users
    async def create_user(self, doc: Dict[str, Any]) -> None:
        await self._mongo.create_user(doc)
        payload = _filter("users", doc)
        await self._mirror_upsert("users", "user_id", payload,
                                   payload.get("user_id"), payload.get("user_id"))

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> None:
        await self._mongo.update_user(user_id, updates)
        user = await self._mongo.get_user_by_id(user_id)
        if user:
            payload = _filter("users", user)
            payload["user_id"] = user_id
            await self._mirror_upsert("users", "user_id", payload, user_id, user_id)

    # Profiles
    async def create_profile(self, doc: Dict[str, Any]) -> None:
        await self._mongo.create_profile(doc)
        payload = _filter("profiles", doc)
        for ts_field in ("exam_date", "last_active_date"):
            v = payload.get(ts_field)
            if v and hasattr(v, "isoformat"):
                payload[ts_field] = v.isoformat()[:10]
        await self._mirror_upsert("profiles", "user_id", payload,
                                   payload.get("user_id"), payload.get("user_id"))

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> None:
        await self._mongo.update_profile(user_id, updates)
        profile = await self._mongo.get_profile(user_id)
        if profile:
            payload = _filter("profiles", profile)
            payload["user_id"] = user_id
            for ts_field in ("exam_date", "last_active_date"):
                v = payload.get(ts_field)
                if v and hasattr(v, "isoformat"):
                    payload[ts_field] = v.isoformat()[:10]
            await self._mirror_upsert("profiles", "user_id", payload, user_id, user_id)

    # Words (only update_word / upsert_word change data worth mirroring)
    async def update_word(self, word_id: str, updates: Dict[str, Any]) -> None:
        await self._mongo.update_word(word_id, updates)
        word = await self._mongo.get_word(word_id)
        if word:
            payload = {k: v for k, v in word.items() if k != "_id"}
            payload["id"] = word_id
            await self._mirror_upsert("words", "id", payload, word_id)

    async def upsert_word(self, word_id: str, doc: Dict[str, Any]) -> None:
        await self._mongo.upsert_word(word_id, doc)
        payload = {k: v for k, v in doc.items() if k != "_id"}
        payload["id"] = word_id
        await self._mirror_upsert("words", "id", payload, word_id)

    # Saved words
    async def save_word(self, user_id: str, word_id: str) -> None:
        await self._mongo.save_word(user_id, word_id)
        payload = {"user_id": user_id, "word_id": word_id, "created_at": _now()}
        await self._mirror_upsert("saved_words", "user_id,word_id",
                                   payload, f"{user_id}:{word_id}", user_id)

    async def unsave_word(self, user_id: str, word_id: str) -> None:
        await self._mongo.unsave_word(user_id, word_id)
        await self._mirror_delete("saved_words", "user_id,word_id",
                                   f"{user_id}:{word_id}", user_id)

    # Progress (delegate mirror to Supabase repo — it handles field mapping)
    async def upsert_word_progress(
        self, user_id: str, word_id: str, doc: Dict[str, Any]
    ) -> None:
        await self._mongo.upsert_word_progress(user_id, word_id, doc)
        try:
            await self._supabase.upsert_word_progress(user_id, word_id, doc)
        except Exception as e:
            log.warning(f"[dw] upsert_word_progress mirror failed: {e}")

    # Atomic XP
    async def increment_user_xp(self, user_id: str, amount: int) -> None:
        await self._mongo.increment_user_xp(user_id, amount)
        try:
            sb = await self._supabase._client()
            await sb.rpc("increment_user_xp", {
                "p_user_id": user_id, "p_amount": amount
            }).execute()
        except Exception as e:
            log.warning(f"[dw] increment_user_xp mirror failed: {e}")

    # Practice session completion
    async def complete_practice_session(
        self,
        user_id: str,
        streak: int,
        longest_streak: int,
        last_active_date: str,
        session_doc: Dict[str, Any],
    ) -> None:
        await self._mongo.complete_practice_session(
            user_id, streak, longest_streak, last_active_date, session_doc
        )
        try:
            await self._supabase.complete_practice_session(
                user_id, streak, longest_streak, last_active_date, session_doc
            )
        except Exception as e:
            log.warning(f"[dw] complete_practice_session mirror failed: {e}")

    # Analytics
    async def log_event(
        self, user_id: str, event: str, props: Dict[str, Any]
    ) -> None:
        await self._mongo.log_event(user_id, event, props)
        try:
            await self._supabase.log_event(user_id, event, props)
        except Exception as e:
            log.warning(f"[dw] log_event mirror failed: {e}")

    # AI coach
    async def insert_ai_coach_content(self, doc: Dict[str, Any]) -> None:
        await self._mongo.insert_ai_coach_content(doc)
        try:
            await self._supabase.insert_ai_coach_content(doc)
        except Exception as e:
            log.warning(f"[dw] insert_ai_coach_content mirror failed: {e}")

    async def insert_ai_coach_usage(self, doc: Dict[str, Any]) -> None:
        await self._mongo.insert_ai_coach_usage(doc)
        try:
            await self._supabase.insert_ai_coach_usage(doc)
        except Exception as e:
            log.warning(f"[dw] insert_ai_coach_usage mirror failed: {e}")

    # TTS cache
    async def insert_tts_cache(self, key: str, audio: bytes) -> None:
        await self._mongo.insert_tts_cache(key, audio)
        try:
            await self._supabase.insert_tts_cache(key, audio)
        except Exception as e:
            log.warning(f"[dw] insert_tts_cache mirror failed: {e}")

    # Subscriptions
    async def activate_subscription(
        self, user_id: str, plan: str, started_at: Any
    ) -> None:
        await self._mongo.activate_subscription(user_id, plan, started_at)
        try:
            await self._supabase.activate_subscription(user_id, plan, started_at)
        except Exception as e:
            log.warning(f"[dw] activate_subscription mirror failed: {e}")

    async def cancel_subscription(self, user_id: str) -> None:
        await self._mongo.cancel_subscription(user_id)
        try:
            await self._supabase.cancel_subscription(user_id)
        except Exception as e:
            log.warning(f"[dw] cancel_subscription mirror failed: {e}")

    # Seed / startup: always Mongo only (content is already seeded in Supabase)
    async def setup_indexes(self) -> None:
        await self._mongo.setup_indexes()

    async def seed_words(self, docs): return await self._mongo.seed_words(docs)
    async def seed_topics(self, docs): return await self._mongo.seed_topics(docs)
    async def seed_exams(self, docs): return await self._mongo.seed_exams(docs)
    async def seed_articles(self, docs): return await self._mongo.seed_articles(docs)

    # ------------------------------------------------------------------
    # Outbox maintenance (operator use)
    # ------------------------------------------------------------------
    async def get_outbox_unresolved(self) -> List[dict]:
        db = self._mongo._db
        return await db.dual_write_outbox.find(
            {"resolved": False}, {"_id": 0}
        ).to_list(1000)

    async def retry_outbox(self, max_retries: int = 5) -> Dict[str, int]:
        """Replay unresolved Supabase mirror writes from the outbox."""
        db = self._mongo._db
        docs = await db.dual_write_outbox.find(
            {"resolved": False, "retry_count": {"$lt": max_retries}},
            {"_id": 0}
        ).to_list(1000)
        resolved = failed = 0
        for doc in docs:
            try:
                sb = await self._supabase._client()
                if doc["operation"] == "upsert":
                    await sb.table(doc["collection"]).upsert(
                        [doc["payload"]],
                        on_conflict=doc["pk_field"],
                        ignore_duplicates=False,
                    ).execute()
                elif doc["operation"] == "delete":
                    q = sb.table(doc["collection"]).delete()
                    for f, v in zip(
                        doc["pk_field"].split(","),
                        str(doc["pk_value"]).split(":"),
                    ):
                        q = q.eq(f.strip(), v)
                    await q.execute()
                await db.dual_write_outbox.update_one(
                    {"op_id": doc["op_id"]},
                    {"$set": {"resolved": True, "resolved_at": _now()}},
                )
                resolved += 1
            except Exception as e:
                await db.dual_write_outbox.update_one(
                    {"op_id": doc["op_id"]},
                    {"$inc": {"retry_count": 1}, "$set": {"error": str(e)}},
                )
                failed += 1
        return {"resolved": resolved, "failed": failed, "total": len(docs)}
