"""
MongoRepository — Motor (async MongoDB) implementation of DatabaseRepository.

Preserves all existing MongoDB behavior exactly.  This is the reference /
rollback implementation.  DB_BACKEND=mongo (default) uses this class.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Set, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from db.base import DatabaseRepository
from vocab_schema import normalize_headword

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "vocably")

_PROJ_NO_ID = {"_id": 0}
_PROJ_ID_ONLY = {"_id": 0, "id": 1}


def _now():
    return datetime.now(timezone.utc)


class MongoRepository(DatabaseRepository):
    def __init__(self):
        self._client = AsyncIOMotorClient(MONGO_URL)
        self._db = self._client[DB_NAME]

    # ------------------------------------------------------------------ #
    # AUTH
    # ------------------------------------------------------------------ #
    async def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        return await self._db.user_sessions.find_one(
            {"session_token": token}, _PROJ_NO_ID
        )

    async def create_session(self, doc: Dict[str, Any]) -> None:
        await self._db.user_sessions.insert_one(doc)

    async def delete_session(self, token: str) -> None:
        await self._db.user_sessions.delete_one({"session_token": token})

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return await self._db.users.find_one({"email": email}, _PROJ_NO_ID)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._db.users.find_one({"user_id": user_id}, _PROJ_NO_ID)

    async def create_user(self, doc: Dict[str, Any]) -> None:
        await self._db.users.insert_one(doc)

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> None:
        await self._db.users.update_one({"user_id": user_id}, {"$set": updates})

    # ------------------------------------------------------------------ #
    # PROFILE
    # ------------------------------------------------------------------ #
    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self._db.profiles.find_one({"user_id": user_id}, _PROJ_NO_ID)

    async def create_profile(self, doc: Dict[str, Any]) -> None:
        await self._db.profiles.insert_one(doc)

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> None:
        await self._db.profiles.update_one({"user_id": user_id}, {"$set": updates})

    # ------------------------------------------------------------------ #
    # WORDS
    # ------------------------------------------------------------------ #
    async def get_word(self, word_id: str) -> Optional[Dict[str, Any]]:
        return await self._db.words.find_one({"id": word_id}, _PROJ_NO_ID)

    async def get_word_by_headword(self, headword: str) -> Optional[Dict[str, Any]]:
        return await self._db.words.find_one({"headword": headword}, _PROJ_NO_ID)

    async def get_word_by_canonical_or_headword(
        self, canonical_key: str, norm: str
    ) -> Optional[Dict[str, Any]]:
        return await self._db.words.find_one(
            {"$or": [{"canonical_key": canonical_key}, {"headword": norm}]},
            {"_id": 0, "id": 1},
        )

    async def word_exists(self, word_id: str) -> bool:
        doc = await self._db.words.find_one({"id": word_id}, {"_id": 1})
        return doc is not None

    async def list_words(
        self,
        search: Optional[str],
        topic: Optional[str],
        cefr: Optional[str],
        exam: Optional[str],
        offset: int,
        limit: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        q: Dict[str, Any] = {"status": "PUBLISHED"}
        if search:
            q["$or"] = [
                {"headword": {"$regex": search, "$options": "i"}},
                {"simple_definition": {"$regex": search, "$options": "i"}},
            ]
        if topic:
            q["topic"] = topic
        if cefr:
            q["cefr"] = cefr
        if exam:
            q["exam_relevance"] = exam
        total = await self._db.words.count_documents(q)
        cursor = (
            self._db.words.find(q, _PROJ_NO_ID)
            .sort("headword", 1)
            .skip(offset)
            .limit(limit)
        )
        words = await cursor.to_list(limit)
        return total, words

    async def find_words_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        return await self._db.words.find(
            {"id": {"$in": ids}}, _PROJ_NO_ID
        ).to_list(len(ids) + 10)

    async def find_words_by_headwords(self, headwords: List[str]) -> List[Dict[str, Any]]:
        if not headwords:
            return []
        return await self._db.words.find(
            {"headword": {"$in": headwords}}, _PROJ_NO_ID
        ).to_list(len(headwords) + 10)

    async def find_published_words_by_exam(self, exam_slug: str) -> List[Dict[str, Any]]:
        return await self._db.words.find(
            {"exam_relevance": exam_slug, "status": "PUBLISHED"}, _PROJ_NO_ID
        ).to_list(500)

    async def find_published_words_by_exam_ids(self, exam_slug: str) -> List[str]:
        docs = await self._db.words.find(
            {"exam_relevance": exam_slug, "status": "PUBLISHED"},
            {"_id": 0, "id": 1},
        ).to_list(500)
        return [d["id"] for d in docs]

    async def find_published_words_by_topic_ids(self, topic: str) -> List[str]:
        docs = await self._db.words.find(
            {"topic": topic, "status": "PUBLISHED"},
            {"_id": 0, "id": 1},
        ).to_list(500)
        return [d["id"] for d in docs]

    async def count_words_by_topic(self, topic: str) -> int:
        return await self._db.words.count_documents(
            {"topic": topic, "status": "PUBLISHED"}
        )

    async def count_words_by_exam(self, exam_slug: str) -> int:
        return await self._db.words.count_documents(
            {"exam_relevance": exam_slug, "status": "PUBLISHED"}
        )

    async def find_published_words(self) -> List[Dict[str, Any]]:
        return await self._db.words.find(
            {"status": "PUBLISHED"}, _PROJ_NO_ID
        ).to_list(2000)

    async def find_words_for_mission(
        self,
        seen_ids: Set[str],
        exam_slug: Optional[str],
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {
            "status": "PUBLISHED",
            "id": {"$nin": list(seen_ids)},
        }
        if exam_slug:
            q["exam_relevance"] = exam_slug
        candidates = await self._db.words.find(q, _PROJ_NO_ID).to_list(500)
        if not candidates and exam_slug:
            del q["exam_relevance"]
            candidates = await self._db.words.find(q, _PROJ_NO_ID).to_list(500)
        return candidates

    async def upsert_word(self, word_id: str, doc: Dict[str, Any]) -> None:
        await self._db.words.update_one(
            {"id": word_id}, {"$set": doc}, upsert=True
        )

    async def update_word(self, word_id: str, updates: Dict[str, Any]) -> None:
        await self._db.words.update_one({"id": word_id}, {"$set": updates})

    async def load_all_words_minimal(self) -> List[Dict[str, Any]]:
        return await self._db.words.find(
            {}, {"_id": 0, "id": 1, "headword": 1}
        ).to_list(200000)

    async def load_all_word_ids(self) -> Set[str]:
        docs = await self._db.words.find({}, {"_id": 0, "id": 1}).to_list(200000)
        return {d["id"] for d in docs if d.get("id")}

    async def load_all_words_full(self) -> List[Dict[str, Any]]:
        return await self._db.words.find({}, _PROJ_NO_ID).to_list(200000)

    # ------------------------------------------------------------------ #
    # GRAPH BATCH  (single query instead of N individual lookups)
    # ------------------------------------------------------------------ #
    async def load_words_for_graph_batch(
        self,
        ref_ids: List[str],
        hw_keys: List[str],
        headwords_lower: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        if not ref_ids and not hw_keys and not headwords_lower:
            return {}
        or_clauses = []
        if ref_ids:
            or_clauses.append({"id": {"$in": ref_ids}})
        if hw_keys:
            or_clauses.append({"canonical_key": {"$in": hw_keys}})
        if headwords_lower:
            or_clauses.append({"headword": {"$in": headwords_lower}})
        q = {"status": "PUBLISHED", "$or": or_clauses}
        words = await self._db.words.find(
            q,
            {"_id": 0, "id": 1, "headword": 1, "cefr": 1,
             "simple_definition": 1, "canonical_key": 1},
        ).to_list(500)
        ref_id_set = set(ref_ids)
        hw_key_set = set(hw_keys)
        headword_set = set(headwords_lower)
        result: Dict[str, Dict[str, Any]] = {}
        for w in words:
            if w.get("id") in ref_id_set:
                result[f"ref:{w['id']}"] = w
            canonical = normalize_headword(w.get("headword", ""))
            if canonical in hw_key_set:
                result[f"hw_key:{canonical}"] = w
            if w.get("headword", "").lower() in headword_set:
                result[f"hw:{w['headword'].lower()}"] = w
        return result

    async def find_words_with_relation_headword(
        self, canonical_key: str
    ) -> List[Dict[str, Any]]:
        from vocab_schema import WORD_RELATION_FIELDS
        or_clauses = [
            {f"relations.{f}": {"$elemMatch": {"headword": canonical_key}}}
            for f in WORD_RELATION_FIELDS
        ]
        return await self._db.words.find(
            {"$or": or_clauses}, _PROJ_NO_ID
        ).to_list(5000)

    async def find_words_needing_lifecycle(self) -> List[Dict[str, Any]]:
        return await self._db.words.find(
            {"lifecycle_version": {"$ne": 1}}, _PROJ_NO_ID
        ).to_list(200000)

    # ------------------------------------------------------------------ #
    # SAVED WORDS
    # ------------------------------------------------------------------ #
    async def get_saved_word_ids(self, user_id: str) -> Set[str]:
        docs = await self._db.saved_words.find(
            {"user_id": user_id}, {"_id": 0, "word_id": 1}
        ).to_list(2000)
        return {d["word_id"] for d in docs}

    async def get_saved_words_sorted(self, user_id: str) -> List[str]:
        docs = await self._db.saved_words.find(
            {"user_id": user_id}, {"_id": 0, "word_id": 1}
        ).sort("created_at", -1).to_list(500)
        return [d["word_id"] for d in docs]

    async def find_saved_word(
        self, user_id: str, word_id: str
    ) -> Optional[Dict[str, Any]]:
        return await self._db.saved_words.find_one(
            {"user_id": user_id, "word_id": word_id}, _PROJ_NO_ID
        )

    async def save_word(self, user_id: str, word_id: str) -> None:
        await self._db.saved_words.update_one(
            {"user_id": user_id, "word_id": word_id},
            {"$set": {"user_id": user_id, "word_id": word_id,
                      "created_at": _now()}},
            upsert=True,
        )

    async def unsave_word(self, user_id: str, word_id: str) -> None:
        await self._db.saved_words.delete_one(
            {"user_id": user_id, "word_id": word_id}
        )

    # ------------------------------------------------------------------ #
    # PROGRESS
    # ------------------------------------------------------------------ #
    async def get_word_progress(
        self, user_id: str, word_id: str
    ) -> Optional[Dict[str, Any]]:
        return await self._db.user_word_progress.find_one(
            {"user_id": user_id, "word_id": word_id}, _PROJ_NO_ID
        )

    async def get_all_progress(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._db.user_word_progress.find(
            {"user_id": user_id}, _PROJ_NO_ID
        ).to_list(5000)

    async def get_progress_by_statuses(
        self, user_id: str, statuses: List[str]
    ) -> List[Dict[str, Any]]:
        return await self._db.user_word_progress.find(
            {"user_id": user_id, "status": {"$in": statuses}}, _PROJ_NO_ID
        ).to_list(3000)

    async def find_progress_by_words(
        self, user_id: str, word_ids: List[str]
    ) -> List[Dict[str, Any]]:
        if not word_ids:
            return []
        return await self._db.user_word_progress.find(
            {"user_id": user_id, "word_id": {"$in": word_ids}}, _PROJ_NO_ID
        ).to_list(len(word_ids) + 10)

    async def upsert_word_progress(
        self, user_id: str, word_id: str, doc: Dict[str, Any]
    ) -> None:
        await self._db.user_word_progress.update_one(
            {"user_id": user_id, "word_id": word_id},
            {"$set": doc},
            upsert=True,
        )

    # ------------------------------------------------------------------ #
    # DOMAIN: ATOMIC XP
    # ------------------------------------------------------------------ #
    async def increment_user_xp(self, user_id: str, amount: int) -> None:
        await self._db.profiles.update_one(
            {"user_id": user_id}, {"$inc": {"xp": amount}}
        )
        await self._db.users.update_one(
            {"user_id": user_id}, {"$inc": {"xp": amount}}
        )

    # ------------------------------------------------------------------ #
    # DOMAIN: PRACTICE SESSION COMPLETION
    # ------------------------------------------------------------------ #
    async def complete_practice_session(
        self,
        user_id: str,
        streak: int,
        longest_streak: int,
        last_active_date: str,
        session_doc: Dict[str, Any],
    ) -> None:
        await self._db.profiles.update_one(
            {"user_id": user_id},
            {"$set": {
                "streak": streak,
                "longest_streak": longest_streak,
                "last_active_date": last_active_date,
            }},
        )
        await self._db.users.update_one(
            {"user_id": user_id}, {"$set": {"streak": streak}}
        )
        await self._db.study_sessions.insert_one(session_doc)

    async def get_study_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        return await self._db.study_sessions.find(
            {"user_id": user_id}, _PROJ_NO_ID
        ).to_list(1000)

    # ------------------------------------------------------------------ #
    # ANALYTICS
    # ------------------------------------------------------------------ #
    async def log_event(
        self, user_id: str, event: str, props: Dict[str, Any]
    ) -> None:
        try:
            await self._db.analytics_events.insert_one({
                "user_id": user_id,
                "event": event,
                "props": props,
                "created_at": _now(),
            })
        except Exception:
            pass

    async def count_ai_coach_today(self, user_id: str) -> int:
        from datetime import date as _date
        today = _date.today().isoformat()
        return await self._db.ai_coach_usage.count_documents(
            {"user_id": user_id, "date": today}
        )

    # ------------------------------------------------------------------ #
    # AI COACH
    # ------------------------------------------------------------------ #
    async def get_ai_coach_content(
        self, word_id: str
    ) -> Optional[Dict[str, Any]]:
        return await self._db.ai_coach_content.find_one(
            {"word_id": word_id}, _PROJ_NO_ID
        )

    async def insert_ai_coach_content(self, doc: Dict[str, Any]) -> None:
        await self._db.ai_coach_content.insert_one(doc)

    async def insert_ai_coach_usage(self, doc: Dict[str, Any]) -> None:
        await self._db.ai_coach_usage.insert_one(doc)

    # ------------------------------------------------------------------ #
    # TTS CACHE
    # ------------------------------------------------------------------ #
    async def tts_cache_exists(self, key: str) -> bool:
        doc = await self._db.tts_cache.find_one({"key": key}, {"_id": 1})
        return doc is not None

    async def get_tts_audio(self, key: str) -> Optional[bytes]:
        doc = await self._db.tts_cache.find_one({"key": key}, _PROJ_NO_ID)
        if not doc:
            return None
        audio = doc.get("audio")
        if audio is None:
            return None
        return bytes(audio)

    async def insert_tts_cache(self, key: str, audio: bytes) -> None:
        await self._db.tts_cache.insert_one({
            "key": key, "audio": audio, "created_at": _now()
        })

    # ------------------------------------------------------------------ #
    # TOPICS / EXAMS / ARTICLES
    # ------------------------------------------------------------------ #
    async def get_topics(self) -> List[Dict[str, Any]]:
        return await self._db.topics.find({}, _PROJ_NO_ID).to_list(100)

    async def get_exams(self) -> List[Dict[str, Any]]:
        return await self._db.exams.find({}, _PROJ_NO_ID).to_list(100)

    async def get_exam_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return await self._db.exams.find_one({"slug": slug}, _PROJ_NO_ID)

    async def find_exams_by_slugs(self, slugs: List[str]) -> List[Dict[str, Any]]:
        if not slugs:
            return []
        return await self._db.exams.find(
            {"slug": {"$in": slugs}}, _PROJ_NO_ID
        ).to_list(20)

    async def get_articles(
        self, level: Optional[str], topic: Optional[str]
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if level:
            q["level"] = level
        if topic:
            q["topic"] = topic
        return await self._db.articles.find(
            q, {"_id": 0, "body": 0}
        ).to_list(100)

    async def get_article_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        return await self._db.articles.find_one(
            {"id": article_id}, _PROJ_NO_ID
        )

    async def get_exam_slugs(self) -> Set[str]:
        docs = await self._db.exams.find(
            {}, {"_id": 0, "slug": 1}
        ).to_list(1000)
        return {d["slug"] for d in docs}

    # ------------------------------------------------------------------ #
    # SUBSCRIPTIONS
    # ------------------------------------------------------------------ #
    async def activate_subscription(
        self, user_id: str, plan: str, started_at: Any
    ) -> None:
        await self._db.users.update_one(
            {"user_id": user_id}, {"$set": {"tier": "pro"}}
        )
        await self._db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id, "plan": plan,
                "status": "active", "platform": "mock",
                "started_at": started_at,
            }},
            upsert=True,
        )

    async def cancel_subscription(self, user_id: str) -> None:
        await self._db.users.update_one(
            {"user_id": user_id}, {"$set": {"tier": "free"}}
        )
        await self._db.subscriptions.update_one(
            {"user_id": user_id}, {"$set": {"status": "cancelled"}}
        )

    # ------------------------------------------------------------------ #
    # SEED / STARTUP
    # ------------------------------------------------------------------ #
    async def count_collection(self, collection: str) -> int:
        return await self._db[collection].count_documents({})

    async def seed_words(self, docs: List[Dict[str, Any]]) -> None:
        if docs:
            await self._db.words.insert_many(docs)

    async def seed_topics(self, docs: List[Dict[str, Any]]) -> None:
        if docs:
            await self._db.topics.insert_many(docs)

    async def seed_exams(self, docs: List[Dict[str, Any]]) -> None:
        if docs:
            await self._db.exams.insert_many(docs)

    async def seed_articles(self, docs: List[Dict[str, Any]]) -> None:
        if docs:
            await self._db.articles.insert_many(docs)

    async def setup_indexes(self) -> None:
        """Create MongoDB indexes required for correct performance."""
        db = self._db
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("user_id")
        await db.user_sessions.create_index(
            "expires_at", expireAfterSeconds=0
        )
        await db.words.create_index("id", unique=True)
        await db.words.create_index("headword")
        await db.words.create_index("topic")
        await db.words.create_index("cefr")
        await db.words.create_index("exam_relevance")
        await db.user_word_progress.create_index(
            [("user_id", 1), ("word_id", 1)], unique=True
        )
        await db.user_word_progress.create_index(
            [("user_id", 1), ("next_review_at", 1)]
        )
        await db.saved_words.create_index(
            [("user_id", 1), ("word_id", 1)], unique=True
        )
        await db.profiles.create_index("user_id", unique=True)
        await db.analytics_events.create_index("user_id")
        # Deferred uniqueness safeguard after canonical backfill
        try:
            await db.words.create_index("canonical_key", unique=True)
        except Exception as e:
            print(f"[mongo] canonical_key unique index skipped: {e}")
