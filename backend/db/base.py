"""
DatabaseRepository base class — domain-level interface that both
MongoRepository and SupabaseRepository must satisfy (duck-typing).
All methods are async coroutines.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


class DatabaseRepository:
    """All methods raise NotImplementedError if not overridden."""

    # ------------------------------------------------------------------ #
    # AUTH — sessions + users
    # ------------------------------------------------------------------ #
    async def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def create_session(self, doc: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def delete_session(self, token: str) -> None:
        raise NotImplementedError

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def create_user(self, doc: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # PROFILE
    # ------------------------------------------------------------------ #
    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def create_profile(self, doc: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def update_profile(self, user_id: str, updates: Dict[str, Any]) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # WORDS
    # ------------------------------------------------------------------ #
    async def get_word(self, word_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def get_word_by_headword(self, headword: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def get_word_by_canonical_or_headword(
        self, canonical_key: str, norm: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def word_exists(self, word_id: str) -> bool:
        raise NotImplementedError

    async def list_words(
        self,
        search: Optional[str],
        topic: Optional[str],
        cefr: Optional[str],
        exam: Optional[str],
        offset: int,
        limit: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        raise NotImplementedError

    async def find_words_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def find_words_by_headwords(self, headwords: List[str]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def find_published_words_by_exam(self, exam_slug: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def find_published_words_by_exam_ids(self, exam_slug: str) -> List[str]:
        """Return word IDs for published words in an exam."""
        raise NotImplementedError

    async def find_published_words_by_topic_ids(self, topic: str) -> List[str]:
        """Return word IDs for published words in a topic."""
        raise NotImplementedError

    async def count_words_by_topic(self, topic: str) -> int:
        raise NotImplementedError

    async def count_words_by_exam(self, exam_slug: str) -> int:
        raise NotImplementedError

    async def find_published_words(self) -> List[Dict[str, Any]]:
        """All published words — used by all_words_cache()."""
        raise NotImplementedError

    async def find_words_for_mission(
        self,
        seen_ids: Set[str],
        exam_slug: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Published words not yet seen by user, optionally filtered by exam."""
        raise NotImplementedError

    async def upsert_word(self, word_id: str, doc: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def update_word(self, word_id: str, updates: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def load_all_words_minimal(self) -> List[Dict[str, Any]]:
        """All words with id + headword — for index building."""
        raise NotImplementedError

    async def load_all_words_full(self) -> List[Dict[str, Any]]:
        """All words with all fields — for migration/resolve passes."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # KNOWLEDGE GRAPH BATCH HELPERS
    # ------------------------------------------------------------------ #
    async def load_words_for_graph_batch(
        self,
        ref_ids: List[str],
        hw_keys: List[str],
        headwords_lower: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Batch-load graph candidates to eliminate N+1 per word detail.
        Returns dict keyed by 'ref:{id}', 'hw_key:{key}', 'hw:{headword}'.
        """
        raise NotImplementedError

    async def find_words_with_relation_headword(
        self, canonical_key: str
    ) -> List[Dict[str, Any]]:
        """Words referencing canonical_key in any relations field."""
        raise NotImplementedError

    async def find_words_needing_lifecycle(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # SAVED WORDS
    # ------------------------------------------------------------------ #
    async def get_saved_word_ids(self, user_id: str) -> Set[str]:
        raise NotImplementedError

    async def get_saved_words_sorted(self, user_id: str) -> List[str]:
        """Return word_ids sorted newest-first."""
        raise NotImplementedError

    async def find_saved_word(
        self, user_id: str, word_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def save_word(self, user_id: str, word_id: str) -> None:
        raise NotImplementedError

    async def unsave_word(self, user_id: str, word_id: str) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # PROGRESS
    # ------------------------------------------------------------------ #
    async def get_word_progress(
        self, user_id: str, word_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def get_all_progress(self, user_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_progress_by_statuses(
        self, user_id: str, statuses: List[str]
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def find_progress_by_words(
        self, user_id: str, word_ids: List[str]
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def upsert_word_progress(
        self, user_id: str, word_id: str, doc: Dict[str, Any]
    ) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # DOMAIN: ATOMIC XP  (users.xp + profiles.xp together)
    # ------------------------------------------------------------------ #
    async def increment_user_xp(self, user_id: str, amount: int) -> None:
        raise NotImplementedError

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
        raise NotImplementedError

    async def get_study_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # ANALYTICS
    # ------------------------------------------------------------------ #
    async def log_event(
        self, user_id: str, event: str, props: Dict[str, Any]
    ) -> None:
        raise NotImplementedError

    async def count_ai_coach_today(self, user_id: str) -> int:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # AI COACH
    # ------------------------------------------------------------------ #
    async def get_ai_coach_content(
        self, word_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def insert_ai_coach_content(self, doc: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def insert_ai_coach_usage(self, doc: Dict[str, Any]) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # TTS CACHE
    # ------------------------------------------------------------------ #
    async def tts_cache_exists(self, key: str) -> bool:
        raise NotImplementedError

    async def get_tts_audio(self, key: str) -> Optional[bytes]:
        """Return raw audio bytes, or None if not cached."""
        raise NotImplementedError

    async def insert_tts_cache(self, key: str, audio: bytes) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # TOPICS / EXAMS / ARTICLES
    # ------------------------------------------------------------------ #
    async def get_topics(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_exams(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_exam_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def find_exams_by_slugs(self, slugs: List[str]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_articles(
        self, level: Optional[str], topic: Optional[str]
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def get_article_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    async def get_exam_slugs(self) -> Set[str]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # SUBSCRIPTIONS  (domain — touches users + subscriptions)
    # ------------------------------------------------------------------ #
    async def activate_subscription(
        self, user_id: str, plan: str, started_at: Any
    ) -> None:
        raise NotImplementedError

    async def cancel_subscription(self, user_id: str) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # SEED / STARTUP
    # ------------------------------------------------------------------ #
    async def count_collection(self, collection: str) -> int:
        raise NotImplementedError

    async def seed_words(self, docs: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    async def seed_topics(self, docs: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    async def seed_exams(self, docs: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    async def seed_articles(self, docs: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    async def setup_indexes(self) -> None:
        """Create DB-specific indexes. No-op for Supabase (indexes are in migrations)."""
        raise NotImplementedError
