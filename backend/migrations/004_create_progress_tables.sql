-- ============================================================
-- MIGRATION 004: Learning Progress Tables
-- Project  : Vocabist → Supabase
-- Purpose  : Per-user vocabulary progress (adaptive learning
--            engine state), saved words, and study sessions.
-- Safety   : Non-destructive. Uses CREATE TABLE IF NOT EXISTS.
-- Depends  : Migration 002 (words), Migration 003 (users)
-- Run via  : Supabase Dashboard → SQL Editor
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 004a. user_word_progress
--   MongoDB: db.user_word_progress  (7 docs at audit time)
--
--   Central adaptive learning state per (user, word) pair.
--   All numeric fields produced by adaptive_learning.py are
--   stored as proper columns so they can be queried directly
--   (e.g. ORDER BY mastery_score, WHERE status = 'RECALLING',
--   WHERE next_review_at <= now()).
--
--   recent_results and last_reason_codes are small bounded
--   arrays → stored as native PostgreSQL arrays, not JSONB.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_word_progress (
    id                      BIGSERIAL   PRIMARY KEY,

    user_id                 TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    word_id                 TEXT        NOT NULL REFERENCES public.words(id)      ON DELETE CASCADE,

    -- ── Status & learning scores ───────────────────────────
    status                  TEXT        NOT NULL DEFAULT 'NEW',
    -- NEW | SEEN | LEARNING | RECALLING | MASTERED

    mastery_score           NUMERIC(5,1) NOT NULL DEFAULT 0,
    -- 0.0 – 100.0 (see adaptive_learning.calculate_mastery_update)

    confidence_score        NUMERIC(5,1) NOT NULL DEFAULT 0,
    -- 0.0 – 100.0

    difficulty              NUMERIC(5,3) NOT NULL DEFAULT 0,
    -- 0.000 – 1.000 (learner-specific, distinct from CEFR)

    -- ── Answer history counters ────────────────────────────
    times_seen              INTEGER     NOT NULL DEFAULT 0,
    times_correct           INTEGER     NOT NULL DEFAULT 0,
    times_wrong             INTEGER     NOT NULL DEFAULT 0,
    consecutive_correct     INTEGER     NOT NULL DEFAULT 0,

    -- ── Spaced repetition state ────────────────────────────
    review_interval         INTEGER     NOT NULL DEFAULT 0,
    -- Days until next review (0 = relearn in minutes after failure)

    last_reviewed_at        TIMESTAMPTZ,
    next_review_at          TIMESTAMPTZ,

    -- ── Response time tracking ─────────────────────────────
    average_response_time   INTEGER     NOT NULL DEFAULT 0,
    -- Milliseconds. Rolling weighted average.

    -- ── Rolling result window & reason codes ──────────────
    recent_results          SMALLINT[]  NOT NULL DEFAULT '{}',
    -- Last 10 answers as 0 (wrong) or 1 (correct). Bounded at RECENT_WINDOW=10.

    last_reason_codes       TEXT[]      NOT NULL DEFAULT '{}',
    -- e.g. ['recent_success', 'high_confidence', 'recalled_after_long_interval']

    -- ── Timestamps ────────────────────────────────────────
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ,

    -- ── Constraints ────────────────────────────────────────
    CONSTRAINT uwp_user_word_unique UNIQUE (user_id, word_id),

    CONSTRAINT uwp_status_check
        CHECK (status IN ('NEW','SEEN','LEARNING','RECALLING','MASTERED')),

    CONSTRAINT uwp_mastery_range
        CHECK (mastery_score    >= 0 AND mastery_score    <= 100),

    CONSTRAINT uwp_confidence_range
        CHECK (confidence_score >= 0 AND confidence_score <= 100),

    CONSTRAINT uwp_difficulty_range
        CHECK (difficulty >= 0 AND difficulty <= 1)
);

COMMENT ON TABLE  public.user_word_progress IS 'Adaptive learning engine state per (user, word). One row per pair, upserted on every /api/practice/answer.';
COMMENT ON COLUMN public.user_word_progress.mastery_score IS '0–100. Demonstrated retention. See adaptive_learning.calculate_mastery_update().';
COMMENT ON COLUMN public.user_word_progress.confidence_score IS '0–100. Reliability/consistency of mastery evidence.';
COMMENT ON COLUMN public.user_word_progress.difficulty IS '0–1. Learner-specific difficulty (NOT CEFR). See adaptive_learning.calculate_difficulty().';
COMMENT ON COLUMN public.user_word_progress.recent_results IS 'Rolling window of last 10 answers: 1=correct, 0=wrong. Bounded at RECENT_WINDOW=10.';
COMMENT ON COLUMN public.user_word_progress.review_interval IS 'Days until next review. 0 = relearn scheduled in minutes (failed answer).';

-- ────────────────────────────────────────────────────────────
-- 004b. saved_words
--   MongoDB: db.saved_words  (2 docs at audit time)
--
--   User bookmarks. Upsert-maintained (upsert=True in Mongo).
--   The unique constraint replaces the compound Mongo index.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.saved_words (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    word_id     TEXT        NOT NULL REFERENCES public.words(id)      ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT saved_words_user_word_unique UNIQUE (user_id, word_id)
);

COMMENT ON TABLE  public.saved_words IS 'User word bookmarks. One row per (user, word). created_at preserved for ordering (/api/saved returns newest first).';

-- ────────────────────────────────────────────────────────────
-- 004c. study_sessions
--   MongoDB: db.study_sessions  (3 docs at audit time)
--
--   Immutable append-only log of completed practice sessions.
--   source matches practice start sources in server.py.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.study_sessions (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    answered    INTEGER     NOT NULL DEFAULT 0,
    correct     INTEGER     NOT NULL DEFAULT 0,
    duration_ms INTEGER     NOT NULL DEFAULT 0,
    source      TEXT        NOT NULL DEFAULT 'mission',
    -- 'mission' | 'exam' | 'topic' | 'word' | 'saved' | 'slipping' | 'import'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.study_sessions IS 'Append-only log of completed practice sessions. Used for streak calculation and study minutes in /api/progress.';
COMMENT ON COLUMN public.study_sessions.source IS 'Session source: mission | exam | topic | word | saved | slipping | import.';
COMMENT ON COLUMN public.study_sessions.duration_ms IS 'Session duration in milliseconds.';
