"""
SupabaseRepository — supabase-py AsyncClient implementation of DatabaseRepository.

Uses the existing 15-table Supabase schema (migrations 001-008).
Uses RPCs for atomic/complex operations:
  - public.increment_user_xp(p_user_id, p_amount)
  - public.find_words_with_relation_headword(p_headword)
  - public.purge_expired_sessions()  [called by pg_cron, not here]

BYTEA (TTS audio): stored as '\\x' + hex string (PostgreSQL hex literal),
read back and converted to Python bytes.

DB_BACKEND=supabase activates this class.
"""
from __future__ import annotations

import os
import time
import base64
from datetime import datetime, timezone, date as _date
from typing import Any, Dict, List, Optional, Set, Tuple

from supabase import create_async_client, AsyncClient
from dotenv import load_dotenv

from db.base import DatabaseRepository
from vocab_schema import normalize_headword

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# TTL for the published-words read-only cache (seconds).
_WORDS_CACHE_TTL = 60.0
_words_cache: Optional[List[Dict[str, Any]]] = None
_words_cache_ts: Optional[float] = None


# ------------------------------------------------------------------ #
# Datetime helpers
# ------------------------------------------------------------------ #

_DT_FIELDS = frozenset({
    "created_at", "updated_at", "expires_at", "last_reviewed_at",
    "next_review_at", "started_at", "cancelled_at",
})


def _str_to_dt(v: Any) -> Any:
    """Convert ISO string from Supabase into an aware datetime."""
    if v is None or isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return v
    return v


def _dt_to_str(v: Any) -> Any:
    """Convert datetime to ISO string for Supabase insert/update."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _normalize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert TIMESTAMPTZ strings to datetime objects in a returned doc."""
    if doc is None:
        return None
    return {
        k: _str_to_dt(v) if k in _DT_FIELDS else v
        for k, v in doc.items()
    }


def _normalize_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_normalize_doc(d) for d in docs if d is not None]


def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare a doc for Supabase insert/update: convert datetimes to ISO strings."""
    result = {}
    for k, v in doc.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, _date) and not isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ------------------------------------------------------------------ #
# BYTEA helpers
# ------------------------------------------------------------------ #

def _bytes_to_pg(b: bytes) -> str:
    """Convert Python bytes to PostgreSQL hex literal string for BYTEA insert."""
    return "\\x" + b.hex()


def _pg_to_bytes(v: Any) -> Optional[bytes]:
    """Convert a PostgreSQL BYTEA value (hex string or bytes) to Python bytes."""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("\\x"):
            try:
                return bytes.fromhex(s[2:])
            except ValueError:
                pass
        # Fallback: try base64 (PostgREST may base64-encode in some versions)
        try:
            return base64.b64decode(s + "==")
        except Exception:
            pass
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SupabaseRepository(DatabaseRepository):
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
                "when DB_BACKEND=supabase."
            )
        self._sb: Optional[AsyncClient] = None

    async def _client(self) -> AsyncClient:
        """Lazily create (and cache) the async Supabase client."""
        if self._sb is None:
            self._sb = await create_async_client(
                SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
            )
        return self._sb

    # ------------------------------------------------------------------ #
    # AUTH
    # ------------------------------------------------------------------ #
    async def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("user_sessions").select("*").eq(
            "session_token", token
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def create_session(self, doc: Dict[str, Any]) -> None:
        sb = await self._client()
        await sb.table("user_sessions").insert(_serialize_doc(doc)).execute()

    async def delete_session(self, token: str) -> None:
        sb = await self._client()
        await sb.table("user_sessions").delete().eq(
            "session_token", token
        ).execute()

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("users").select("*").eq(
            "email", email
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("users").select("*").eq(
            "user_id", user_id
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def create_user(self, doc: Dict[str, Any]) -> None:
        sb = await self._client()
        await sb.table("users").insert(_serialize_doc(doc)).execute()

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> None:
        sb = await self._client()
        await sb.table("users").update(
            _serialize_doc(updates)
        ).eq("user_id", user_id).execute()

    # ------------------------------------------------------------------ #
    # PROFILE
    # ------------------------------------------------------------------ #
    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("profiles").select("*").eq(
            "user_id", user_id
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def create_profile(self, doc: Dict[str, Any]) -> None:
        sb = await self._client()
        # Use upsert with ignore_duplicates to handle race conditions
        await sb.table("profiles").upsert(
            _serialize_doc(doc), on_conflict="user_id", ignore_duplicates=True
        ).execute()

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> None:
        sb = await self._client()
        await sb.table("profiles").update(
            _serialize_doc(updates)
        ).eq("user_id", user_id).execute()

    # ------------------------------------------------------------------ #
    # WORDS
    # ------------------------------------------------------------------ #
    async def get_word(self, word_id: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("*").eq(
            "id", word_id
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def get_word_by_headword(self, headword: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("*").eq(
            "headword", headword
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def get_word_by_canonical_or_headword(
        self, canonical_key: str, norm: str
    ) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("id").or_(
            f"canonical_key.eq.{canonical_key},headword.eq.{norm}"
        ).limit(1).execute()
        docs = r.data or []
        return _normalize_doc(docs[0]) if docs else None

    async def word_exists(self, word_id: str) -> bool:
        sb = await self._client()
        r = await sb.table("words").select("id").eq(
            "id", word_id
        ).maybe_single().execute()
        return r is not None and r.data is not None

    async def list_words(
        self,
        search: Optional[str],
        topic: Optional[str],
        cefr: Optional[str],
        exam: Optional[str],
        offset: int,
        limit: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        sb = await self._client()
        q = sb.table("words").select("*", count="exact").eq("status", "PUBLISHED")
        if search:
            q = q.or_(
                f"headword.ilike.%{search}%,"
                f"simple_definition.ilike.%{search}%"
            )
        if topic:
            q = q.eq("topic", topic)
        if cefr:
            q = q.eq("cefr", cefr)
        if exam:
            q = q.contains("exam_relevance", [exam])
        end = offset + limit - 1
        r = await q.order("headword").range(offset, end).execute()
        return (r.count or 0), _normalize_docs(r.data or [])

    async def find_words_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        sb = await self._client()
        r = await sb.table("words").select("*").in_("id", ids).execute()
        return _normalize_docs(r.data or [])

    async def find_words_by_headwords(self, headwords: List[str]) -> List[Dict[str, Any]]:
        if not headwords:
            return []
        sb = await self._client()
        r = await sb.table("words").select("*").in_("headword", headwords).execute()
        return _normalize_docs(r.data or [])

    async def find_published_words_by_exam(self, exam_slug: str) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("*").eq(
            "status", "PUBLISHED"
        ).contains("exam_relevance", [exam_slug]).execute()
        return _normalize_docs(r.data or [])

    async def find_published_words_by_exam_ids(self, exam_slug: str) -> List[str]:
        sb = await self._client()
        r = await sb.table("words").select("id").eq(
            "status", "PUBLISHED"
        ).contains("exam_relevance", [exam_slug]).execute()
        return [d["id"] for d in (r.data or [])]

    async def find_published_words_by_topic_ids(self, topic: str) -> List[str]:
        sb = await self._client()
        r = await sb.table("words").select("id").eq(
            "status", "PUBLISHED"
        ).eq("topic", topic).execute()
        return [d["id"] for d in (r.data or [])]

    async def count_words_by_topic(self, topic: str) -> int:
        sb = await self._client()
        r = await sb.table("words").select(
            "id", count="exact"
        ).eq("status", "PUBLISHED").eq("topic", topic).execute()
        return r.count or 0

    async def count_words_by_exam(self, exam_slug: str) -> int:
        sb = await self._client()
        r = await sb.table("words").select(
            "id", count="exact"
        ).eq("status", "PUBLISHED").contains("exam_relevance", [exam_slug]).execute()
        return r.count or 0

    async def find_published_words(self) -> List[Dict[str, Any]]:
        """All published words with a 60-second in-process TTL cache."""
        global _words_cache, _words_cache_ts
        now = time.monotonic()
        if (
            _words_cache is not None
            and _words_cache_ts is not None
            and (now - _words_cache_ts) < _WORDS_CACHE_TTL
        ):
            return _words_cache
        sb = await self._client()
        r = await sb.table("words").select("*").eq("status", "PUBLISHED").execute()
        _words_cache = _normalize_docs(r.data or [])
        _words_cache_ts = now
        return _words_cache

    async def find_words_for_mission(
        self,
        seen_ids: Set[str],
        exam_slug: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Use cached published words + Python-side filter to avoid $nin URL limits."""
        all_published = await self.find_published_words()
        candidates = [w for w in all_published if w["id"] not in seen_ids]
        if exam_slug:
            exam_candidates = [
                w for w in candidates
                if exam_slug in (w.get("exam_relevance") or [])
            ]
            if exam_candidates:
                return exam_candidates
        return candidates

    async def upsert_word(self, word_id: str, doc: Dict[str, Any]) -> None:
        sb = await self._client()
        clean = _serialize_doc({**doc, "id": word_id})
        # Remove None values that violate NOT NULL constraints with defaults
        # (Supabase upsert will use column defaults for absent fields)
        await sb.table("words").upsert(clean, on_conflict="id").execute()

    async def update_word(self, word_id: str, updates: Dict[str, Any]) -> None:
        sb = await self._client()
        await sb.table("words").update(
            _serialize_doc(updates)
        ).eq("id", word_id).execute()

    async def load_all_words_minimal(self) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("id,headword").execute()
        return r.data or []

    async def load_all_word_ids(self) -> Set[str]:
        """Single bulk query — avoids N individual HTTP round-trips."""
        sb = await self._client()
        r = await sb.table("words").select("id").execute()
        return {row["id"] for row in (r.data or []) if row.get("id")}

    async def load_all_words_full(self) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("*").execute()
        return _normalize_docs(r.data or [])

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
        sb = await self._client()

        # Build PostgREST OR filter string
        parts = []
        if ref_ids:
            parts.append("id.in.({})".format(",".join(ref_ids)))
        if hw_keys:
            parts.append("canonical_key.in.({})".format(",".join(hw_keys)))
        if headwords_lower:
            parts.append("headword.in.({})".format(",".join(headwords_lower)))

        or_str = ",".join(parts)
        r = await sb.table("words").select(
            "id,headword,cefr,simple_definition,canonical_key"
        ).eq("status", "PUBLISHED").or_(or_str).execute()

        ref_id_set = set(ref_ids)
        hw_key_set = set(hw_keys)
        headword_set = set(headwords_lower)
        result: Dict[str, Dict[str, Any]] = {}
        for w in (r.data or []):
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
        """Use the find_words_with_relation_headword RPC for JSONB search."""
        sb = await self._client()
        r = await sb.rpc(
            "find_words_with_relation_headword",
            {"p_headword": canonical_key},
        ).execute()
        return _normalize_docs(r.data or [])

    async def find_words_needing_lifecycle(self) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("words").select("*").neq("lifecycle_version", 1).execute()
        return _normalize_docs(r.data or [])

    # ------------------------------------------------------------------ #
    # SAVED WORDS
    # ------------------------------------------------------------------ #
    async def get_saved_word_ids(self, user_id: str) -> Set[str]:
        sb = await self._client()
        r = await sb.table("saved_words").select("word_id").eq(
            "user_id", user_id
        ).execute()
        return {d["word_id"] for d in (r.data or [])}

    async def get_saved_words_sorted(self, user_id: str) -> List[str]:
        sb = await self._client()
        r = await sb.table("saved_words").select("word_id").eq(
            "user_id", user_id
        ).order("created_at", desc=True).execute()
        return [d["word_id"] for d in (r.data or [])]

    async def find_saved_word(
        self, user_id: str, word_id: str
    ) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("saved_words").select("*").eq(
            "user_id", user_id
        ).eq("word_id", word_id).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def save_word(self, user_id: str, word_id: str) -> None:
        sb = await self._client()
        await sb.table("saved_words").upsert(
            {"user_id": user_id, "word_id": word_id,
             "created_at": _now().isoformat()},
            on_conflict="user_id,word_id",
        ).execute()

    async def unsave_word(self, user_id: str, word_id: str) -> None:
        sb = await self._client()
        await sb.table("saved_words").delete().eq(
            "user_id", user_id
        ).eq("word_id", word_id).execute()

    # ------------------------------------------------------------------ #
    # PROGRESS
    # ------------------------------------------------------------------ #
    async def get_word_progress(
        self, user_id: str, word_id: str
    ) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("user_word_progress").select("*").eq(
            "user_id", user_id
        ).eq("word_id", word_id).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def get_all_progress(self, user_id: str) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("user_word_progress").select("*").eq(
            "user_id", user_id
        ).execute()
        return _normalize_docs(r.data or [])

    async def get_progress_by_statuses(
        self, user_id: str, statuses: List[str]
    ) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("user_word_progress").select("*").eq(
            "user_id", user_id
        ).in_("status", statuses).execute()
        return _normalize_docs(r.data or [])

    async def find_progress_by_words(
        self, user_id: str, word_ids: List[str]
    ) -> List[Dict[str, Any]]:
        if not word_ids:
            return []
        sb = await self._client()
        r = await sb.table("user_word_progress").select("*").eq(
            "user_id", user_id
        ).in_("word_id", word_ids).execute()
        return _normalize_docs(r.data or [])

    async def upsert_word_progress(
        self, user_id: str, word_id: str, doc: Dict[str, Any]
    ) -> None:
        sb = await self._client()
        clean = _serialize_doc(doc)
        # Ensure identity fields are present for the ON CONFLICT clause
        clean["user_id"] = user_id
        clean["word_id"] = word_id
        # Remove BIGSERIAL 'id' — never set it on upsert
        clean.pop("id", None)
        await sb.table("user_word_progress").upsert(
            clean, on_conflict="user_id,word_id"
        ).execute()

    # ------------------------------------------------------------------ #
    # DOMAIN: ATOMIC XP  (single RPC — prevents dual-write divergence)
    # ------------------------------------------------------------------ #
    async def increment_user_xp(self, user_id: str, amount: int) -> None:
        sb = await self._client()
        await sb.rpc(
            "increment_user_xp",
            {"p_user_id": user_id, "p_amount": amount},
        ).execute()

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
        sb = await self._client()
        await sb.table("profiles").update({
            "streak": streak,
            "longest_streak": longest_streak,
            "last_active_date": last_active_date,
        }).eq("user_id", user_id).execute()
        await sb.table("users").update(
            {"streak": streak}
        ).eq("user_id", user_id).execute()
        clean = _serialize_doc(session_doc)
        clean.pop("id", None)
        await sb.table("study_sessions").insert(clean).execute()

    async def get_study_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("study_sessions").select("*").eq(
            "user_id", user_id
        ).execute()
        return _normalize_docs(r.data or [])

    # ------------------------------------------------------------------ #
    # ANALYTICS
    # ------------------------------------------------------------------ #
    async def log_event(
        self, user_id: str, event: str, props: Dict[str, Any]
    ) -> None:
        try:
            sb = await self._client()
            await sb.table("analytics_events").insert({
                "user_id": user_id,
                "event": event,
                "props": props,
                "created_at": _now().isoformat(),
            }).execute()
        except Exception:
            pass

    async def count_ai_coach_today(self, user_id: str) -> int:
        today = _date.today().isoformat()
        sb = await self._client()
        r = await sb.table("ai_coach_usage").select(
            "id", count="exact"
        ).eq("user_id", user_id).eq("date", today).execute()
        return r.count or 0

    # ------------------------------------------------------------------ #
    # AI COACH
    # ------------------------------------------------------------------ #
    async def get_ai_coach_content(
        self, word_id: str
    ) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("ai_coach_content").select("*").eq(
            "word_id", word_id
        ).maybe_single().execute()
        return _normalize_doc(r.data if r is not None else None)

    async def insert_ai_coach_content(self, doc: Dict[str, Any]) -> None:
        sb = await self._client()
        clean = _serialize_doc(doc)
        clean.pop("id", None)
        await sb.table("ai_coach_content").insert(clean).execute()

    async def insert_ai_coach_usage(self, doc: Dict[str, Any]) -> None:
        sb = await self._client()
        clean = _serialize_doc(doc)
        clean.pop("id", None)
        await sb.table("ai_coach_usage").insert(clean).execute()

    # ------------------------------------------------------------------ #
    # TTS CACHE — explicit BYTEA hex encoding for PostgREST JSON layer
    # ------------------------------------------------------------------ #
    async def tts_cache_exists(self, key: str) -> bool:
        sb = await self._client()
        r = await sb.table("tts_cache").select("key").eq(
            "key", key
        ).maybe_single().execute()
        return r is not None and r.data is not None

    async def get_tts_audio(self, key: str) -> Optional[bytes]:
        sb = await self._client()
        r = await sb.table("tts_cache").select("audio").eq(
            "key", key
        ).maybe_single().execute()
        if r is None:
            return None
        return _pg_to_bytes(r.data.get("audio"))

    async def insert_tts_cache(self, key: str, audio: bytes) -> None:
        sb = await self._client()
        await sb.table("tts_cache").insert({
            "key": key,
            "audio": _bytes_to_pg(audio),
            "created_at": _now().isoformat(),
        }).execute()

    # ------------------------------------------------------------------ #
    # TOPICS / EXAMS / ARTICLES
    # ------------------------------------------------------------------ #
    async def get_topics(self) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("topics").select("*").execute()
        return r.data or []

    async def get_exams(self) -> List[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("exams").select("*").execute()
        return r.data or []

    async def get_exam_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("exams").select("*").eq(
            "slug", slug
        ).maybe_single().execute()
        return r.data if r is not None else None

    async def find_exams_by_slugs(self, slugs: List[str]) -> List[Dict[str, Any]]:
        if not slugs:
            return []
        sb = await self._client()
        r = await sb.table("exams").select("*").in_("slug", slugs).execute()
        return r.data or []

    async def get_articles(
        self, level: Optional[str], topic: Optional[str]
    ) -> List[Dict[str, Any]]:
        sb = await self._client()
        q = sb.table("articles").select(
            "id,title,level,topic,minutes,excerpt,created_at"
        )
        if level:
            q = q.eq("level", level)
        if topic:
            q = q.eq("topic", topic)
        r = await q.execute()
        return r.data or []

    async def get_article_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        sb = await self._client()
        r = await sb.table("articles").select("*").eq(
            "id", article_id
        ).maybe_single().execute()
        return r.data if r is not None else None

    async def get_exam_slugs(self) -> Set[str]:
        sb = await self._client()
        r = await sb.table("exams").select("slug").execute()
        return {d["slug"] for d in (r.data or [])}

    # ------------------------------------------------------------------ #
    # SUBSCRIPTIONS
    # ------------------------------------------------------------------ #
    async def activate_subscription(
        self, user_id: str, plan: str, started_at: Any
    ) -> None:
        sb = await self._client()
        await sb.table("users").update(
            {"tier": "pro"}
        ).eq("user_id", user_id).execute()
        started_str = started_at.isoformat() if isinstance(started_at, datetime) else str(started_at)
        await sb.table("subscriptions").upsert({
            "user_id": user_id,
            "plan": plan,
            "status": "active",
            "platform": "mock",
            "started_at": started_str,
        }, on_conflict="user_id").execute()

    async def cancel_subscription(self, user_id: str) -> None:
        sb = await self._client()
        await sb.table("users").update(
            {"tier": "free"}
        ).eq("user_id", user_id).execute()
        await sb.table("subscriptions").update(
            {"status": "cancelled"}
        ).eq("user_id", user_id).execute()

    # ------------------------------------------------------------------ #
    # SEED / STARTUP
    # ------------------------------------------------------------------ #
    async def count_collection(self, collection: str) -> int:
        sb = await self._client()
        r = await sb.table(collection).select("*", count="exact").limit(1).execute()
        return r.count or 0

    async def seed_words(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        sb = await self._client()
        clean = [_serialize_doc(d) for d in docs]
        # Upsert by id to be idempotent
        await sb.table("words").upsert(clean, on_conflict="id").execute()

    async def seed_topics(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        sb = await self._client()
        await sb.table("topics").upsert(
            [_serialize_doc(d) for d in docs], on_conflict="slug"
        ).execute()

    async def seed_exams(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        sb = await self._client()
        await sb.table("exams").upsert(
            [_serialize_doc(d) for d in docs], on_conflict="slug"
        ).execute()

    async def seed_articles(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        sb = await self._client()
        await sb.table("articles").upsert(
            [_serialize_doc(d) for d in docs], on_conflict="id"
        ).execute()

    async def setup_indexes(self) -> None:
        """No-op for Supabase — indexes are created by migration SQL files."""
        pass
