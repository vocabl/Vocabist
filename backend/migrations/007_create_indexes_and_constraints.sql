-- ============================================================
-- MIGRATION 007: Indexes, Unique Constraints & Triggers
-- Project  : Vocabist → Supabase
-- Purpose  : Add all performance indexes, enforce uniqueness
--            that could not be declared inline, and add
--            automatic updated_at trigger.
-- Safety   : Non-destructive. All CREATE INDEX use IF NOT EXISTS.
-- Depends  : Migrations 001–006 (all tables must exist)
-- Run via  : Supabase Dashboard → SQL Editor
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- A. words indexes
-- ────────────────────────────────────────────────────────────

-- Canonical key uniqueness (Phase A guarantee from vocab_schema.py)
CREATE UNIQUE INDEX IF NOT EXISTS words_canonical_key_unique
    ON public.words (canonical_key);

-- Headword lookup (list_words search, ensure_word dedupe)
CREATE INDEX IF NOT EXISTS words_headword_idx
    ON public.words (headword);

-- Status filter (all published word queries use status = 'PUBLISHED')
CREATE INDEX IF NOT EXISTS words_status_idx
    ON public.words (status);

-- Topic filter (GET /api/topics, GET /api/words?topic=...)
CREATE INDEX IF NOT EXISTS words_topic_idx
    ON public.words (topic);

-- CEFR filter (GET /api/words?cefr=B2)
CREATE INDEX IF NOT EXISTS words_cefr_idx
    ON public.words (cefr);

-- Exam relevance array filter (GIN)
-- Replaces MongoDB: db.words.create_index('exam_relevance')
-- Query pattern: WHERE exam_relevance @> ARRAY['gre']
--            or: WHERE 'gre' = ANY(exam_relevance)
CREATE INDEX IF NOT EXISTS words_exam_relevance_gin
    ON public.words USING GIN (exam_relevance);

-- Full-text search on headword + definition
-- Replaces MongoDB $regex queries on headword/simple_definition
CREATE INDEX IF NOT EXISTS words_fts_idx
    ON public.words USING GIN (
        to_tsvector('english',
            COALESCE(headword, '') || ' ' ||
            COALESCE(simple_definition, ''))
    );

-- JSONB relations for graph resolution queries
CREATE INDEX IF NOT EXISTS words_relations_gin
    ON public.words USING GIN (relations);

-- ────────────────────────────────────────────────────────────
-- B. users indexes
-- ────────────────────────────────────────────────────────────

-- Email lookup (login, registration dedupe)
-- Unique constraint already declared inline; btree for speed
CREATE INDEX IF NOT EXISTS users_email_idx
    ON public.users (email);

-- Tier filter (entitlement checks)
CREATE INDEX IF NOT EXISTS users_tier_idx
    ON public.users (tier);

-- ────────────────────────────────────────────────────────────
-- C. user_sessions indexes
-- ────────────────────────────────────────────────────────────

-- Session token lookup (every authenticated request)
-- Unique declared inline; explicit btree for planner
CREATE INDEX IF NOT EXISTS user_sessions_token_idx
    ON public.user_sessions (session_token);

-- User → sessions (logout, session audit)
CREATE INDEX IF NOT EXISTS user_sessions_user_idx
    ON public.user_sessions (user_id);

-- Expired session cleanup (periodic DELETE WHERE expires_at < now())
-- Replaces MongoDB TTL index: expireAfterSeconds=0
CREATE INDEX IF NOT EXISTS user_sessions_expires_idx
    ON public.user_sessions (expires_at);

-- ────────────────────────────────────────────────────────────
-- D. user_word_progress indexes
-- ────────────────────────────────────────────────────────────

-- Compound lookup (was compound Mongo unique index)
CREATE INDEX IF NOT EXISTS uwp_user_word_idx
    ON public.user_word_progress (user_id, word_id);

-- Due-for-review mission selection:
-- WHERE user_id=$1 AND next_review_at <= now() AND status != 'MASTERED'
CREATE INDEX IF NOT EXISTS uwp_review_queue_idx
    ON public.user_word_progress (user_id, next_review_at)
    WHERE status != 'MASTERED';

-- Status filter (LEARNING/RECALLING continue card, progress page)
CREATE INDEX IF NOT EXISTS uwp_status_idx
    ON public.user_word_progress (user_id, status);

-- Mastery score sorting (weak area analysis in /api/progress)
CREATE INDEX IF NOT EXISTS uwp_mastery_idx
    ON public.user_word_progress (user_id, mastery_score);

-- ────────────────────────────────────────────────────────────
-- E. saved_words indexes
-- ────────────────────────────────────────────────────────────

-- User bookmarks list (ordered by saved date, newest first)
CREATE INDEX IF NOT EXISTS saved_words_user_idx
    ON public.saved_words (user_id, created_at DESC);

-- ────────────────────────────────────────────────────────────
-- F. study_sessions indexes
-- ────────────────────────────────────────────────────────────

-- User sessions list and duration sum (/api/progress)
CREATE INDEX IF NOT EXISTS study_sessions_user_idx
    ON public.study_sessions (user_id, created_at DESC);

-- ────────────────────────────────────────────────────────────
-- G. analytics_events indexes
-- ────────────────────────────────────────────────────────────

-- Per-user event queries
CREATE INDEX IF NOT EXISTS analytics_user_idx
    ON public.analytics_events (user_id, created_at DESC);

-- Event type filtering
CREATE INDEX IF NOT EXISTS analytics_event_idx
    ON public.analytics_events (event, created_at DESC);

-- JSONB props search (future analytics queries on payload)
CREATE INDEX IF NOT EXISTS analytics_props_gin
    ON public.analytics_events USING GIN (props);

-- ────────────────────────────────────────────────────────────
-- H. ai_coach_usage indexes
-- ────────────────────────────────────────────────────────────

-- Daily count query: WHERE user_id=$1 AND date=CURRENT_DATE
CREATE INDEX IF NOT EXISTS ai_usage_user_date_idx
    ON public.ai_coach_usage (user_id, date);

-- ────────────────────────────────────────────────────────────
-- I. articles indexes
-- ────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS articles_level_idx
    ON public.articles (level);

CREATE INDEX IF NOT EXISTS articles_topic_idx
    ON public.articles (topic);

-- ────────────────────────────────────────────────────────────
-- J. Automatic updated_at trigger
--    Sets updated_at = now() on every UPDATE for tables that
--    have an updated_at column: users, profiles, subscriptions,
--    user_word_progress, words.
-- ────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.set_updated_at() IS 'Trigger function: sets updated_at = now() before every UPDATE.';

-- Apply trigger to each table with an updated_at column
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['users','profiles','subscriptions','user_word_progress','words']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'trg_' || t || '_updated_at'
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER trg_%I_updated_at
                 BEFORE UPDATE ON public.%I
                 FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()',
                t, t
            );
        END IF;
    END LOOP;
END;
$$;
