-- ============================================================
-- VOCABIST — CONSOLIDATED SUPABASE MIGRATION
-- Version   : 1.0.0
-- Generated : 2026-06-26 (Final Preflight, Stage 1)
-- Purpose   : Single-file migration for Supabase Dashboard
--             SQL Editor.
-- Source    : Combines migrations 001–007 in dependency order,
--             plus one correction from the Final Preflight audit.
-- ============================================================
--
-- SAFETY GUARANTEES:
--   ✅ All CREATE TABLE use  IF NOT EXISTS
--   ✅ All CREATE INDEX use  IF NOT EXISTS
--   ✅ No DROP, TRUNCATE, DELETE statements
--   ✅ No data modification (INSERT / UPDATE)
--   ✅ Safe to re-run on the same schema
--   ✅ No Supabase project reset
--
-- PREFLIGHT CORRECTIONS INCLUDED:
--   🔧 Added pg_trgm extension + trigram GIN indexes on
--      words.headword and words.simple_definition so that
--      the existing FastAPI ILIKE / $regex search pattern
--      works with a supporting index after Stage 3 switchover.
--      (The tsvector index from the original 007 is kept
--       as an additive enhancement for future full-text search.)
--
-- HOW TO RUN:
--   1. Open https://app.supabase.com → SQL Editor
--   2. Paste this entire file
--   3. Click Run
--   4. Verify: "Success. No rows returned." in the output panel
-- ============================================================

-- ============================================================
-- PRE-FLIGHT: Required extensions
-- ============================================================
-- pg_trgm: enables GIN trigram indexes for ILIKE '%term%'
-- (pre-installed on all Supabase projects)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- MIGRATION 001 — Reference / Lookup Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS public.topics (
    slug        TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,
    icon        TEXT,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.topics IS 'Vocabulary topic taxonomy. Slug is the stable FK used by words.topic.';
COMMENT ON COLUMN public.topics.slug IS 'Unique machine-readable key. Matches words.topic.';

CREATE TABLE IF NOT EXISTS public.exams (
    slug        TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,
    full_name   TEXT,
    category    TEXT,
    score_type  TEXT,
    max_score   NUMERIC(6,1),
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.exams IS 'Supported exam list. Slug is FK for words.exam_relevance[] and profiles.exam_slug.';
COMMENT ON COLUMN public.exams.max_score IS 'E.g. 9.0 for IELTS, 120 for TOEFL, 340 for GRE.';

CREATE TABLE IF NOT EXISTS public.articles (
    id          TEXT        PRIMARY KEY,
    title       TEXT        NOT NULL,
    level       TEXT,
    topic       TEXT        REFERENCES public.topics(slug) ON DELETE SET NULL,
    minutes     INTEGER,
    excerpt     TEXT,
    body        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.articles IS 'Short reading articles for the Read & Learn feature.';
COMMENT ON COLUMN public.articles.level IS 'CEFR reading level: A1, A2, B1, B2, C1, C2.';
COMMENT ON COLUMN public.articles.topic IS 'FK to topics.slug. NULL if topic is deleted.';

-- ============================================================
-- MIGRATION 002 — Canonical Words Table
-- ============================================================

CREATE TABLE IF NOT EXISTS public.words (

    -- Identity
    id                  TEXT        PRIMARY KEY,
    headword            TEXT        NOT NULL,
    canonical_key       TEXT        NOT NULL,

    -- Core metadata
    part_of_speech      TEXT,
    cefr                TEXT,
    frequency           SMALLINT,
    academic_importance SMALLINT,
    topic               TEXT        REFERENCES public.topics(slug) ON DELETE SET NULL,

    -- Definitions
    simple_definition   TEXT,
    easy_meaning        TEXT,
    detailed_definition TEXT,
    example             TEXT,
    easy_example        TEXT,
    mnemonic            TEXT,
    common_mistakes     TEXT,
    usage_notes         TEXT,

    -- Phonetics (flat legacy)
    phonetic            TEXT,
    phonetic_us         TEXT,
    phonetic_uk         TEXT,

    -- Flat legacy relation arrays (simple strings)
    -- NOTE: One word ('serendipity') has NULL for these in MongoDB.
    --       Data migration must COALESCE(field, ARRAY[]::TEXT[]) for all.
    synonyms            TEXT[]      NOT NULL DEFAULT '{}',
    antonyms            TEXT[]      NOT NULL DEFAULT '{}',
    related             TEXT[]      NOT NULL DEFAULT '{}',
    confusing_words     TEXT[]      NOT NULL DEFAULT '{}',
    word_family         TEXT[]      NOT NULL DEFAULT '{}',
    roots               TEXT[]      NOT NULL DEFAULT '{}',
    prefixes            TEXT[]      NOT NULL DEFAULT '{}',
    suffixes            TEXT[]      NOT NULL DEFAULT '{}',

    -- Exam & school relevance
    -- NOTE: 'serendipity' also has NULL exam_relevance — same COALESCE fix applies.
    exam_relevance      TEXT[]      NOT NULL DEFAULT '{}',

    -- Structured nested fields (JSONB)
    meanings            JSONB,
    pronunciation       JSONB,
    relations           JSONB,
    audio               JSONB,
    translations        JSONB,
    contextual_examples JSONB,
    school_relevance    JSONB,

    -- Content lifecycle
    status              TEXT        NOT NULL DEFAULT 'PUBLISHED',
    provenance          TEXT        NOT NULL DEFAULT 'CURATED',
    provenance_original TEXT,
    lifecycle_version   SMALLINT    NOT NULL DEFAULT 1,
    schema_version      SMALLINT    NOT NULL DEFAULT 1,

    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT words_status_check
        CHECK (status IN ('DRAFT', 'REVIEW', 'PUBLISHED', 'ARCHIVED')),

    CONSTRAINT words_cefr_check
        CHECK (cefr IS NULL OR cefr IN ('A1','A2','B1','B2','C1','C2')),

    CONSTRAINT words_provenance_check
        CHECK (provenance IN ('CURATED','AI_GENERATED','IMPORTED','ADMIN_CREATED','SEED'))
);

COMMENT ON TABLE  public.words IS 'Canonical vocabulary table. id is the slug-based PK. canonical_key is the normalised uniqueness key.';
COMMENT ON COLUMN public.words.id IS 'Slug-based canonical word ID, e.g. "abate". Stable across migrations.';
COMMENT ON COLUMN public.words.canonical_key IS 'Lower-cased, whitespace-collapsed headword. Unique index in migration 007.';
COMMENT ON COLUMN public.words.exam_relevance IS 'Array of exam slugs. GIN indexed. Query: WHERE exam_relevance @> ARRAY[''gre'']';
COMMENT ON COLUMN public.words.status IS 'Content lifecycle: DRAFT | REVIEW | PUBLISHED | ARCHIVED';
COMMENT ON COLUMN public.words.provenance IS 'Content origin: CURATED | AI_GENERATED | IMPORTED | ADMIN_CREATED | SEED';

-- ============================================================
-- MIGRATION 003 — User & Auth Tables
-- NOTE: custom user_id TEXT (NOT Supabase auth.users UUID).
--       Auth migration is a separate future stage.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.users (
    user_id         TEXT        PRIMARY KEY,
    email           TEXT        NOT NULL,
    name            TEXT,
    picture         TEXT,
    password_hash   TEXT,
    onboarded       BOOLEAN     NOT NULL DEFAULT FALSE,
    tier            TEXT        NOT NULL DEFAULT 'free',
    xp              INTEGER     NOT NULL DEFAULT 0,
    streak          INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,

    CONSTRAINT users_email_unique UNIQUE (email),
    CONSTRAINT users_tier_check   CHECK (tier IN ('free', 'pro'))
);

COMMENT ON TABLE  public.users IS 'Application users. user_id = "user_"+hex(6). NOT Supabase auth.users.id. Auth migration is a separate phase.';
COMMENT ON COLUMN public.users.password_hash IS 'bcrypt hash. NULL for Google-OAuth users.';

CREATE TABLE IF NOT EXISTS public.user_sessions (
    id              BIGSERIAL   PRIMARY KEY,
    session_token   TEXT        NOT NULL UNIQUE,
    user_id         TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE  public.user_sessions IS 'Bearer token sessions (7-day TTL). Purge expired: DELETE FROM user_sessions WHERE expires_at < now();';

CREATE TABLE IF NOT EXISTS public.profiles (
    user_id         TEXT        PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,
    reason          TEXT,
    level           TEXT,
    daily_minutes   INTEGER     NOT NULL DEFAULT 10,
    exam_slug       TEXT        REFERENCES public.exams(slug) ON DELETE SET NULL,
    -- NOTE: exam_date stored as ISO string 'YYYY-MM-DD' in MongoDB.
    --       Data migration must cast: exam_date::DATE.
    exam_date       DATE,
    target_score    NUMERIC(6,2),
    streak          INTEGER     NOT NULL DEFAULT 0,
    longest_streak  INTEGER     NOT NULL DEFAULT 0,
    xp              INTEGER     NOT NULL DEFAULT 0,
    last_active_date DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

COMMENT ON TABLE  public.profiles IS 'One-to-one extension of users. Onboarding, exam goals, streak and XP mirror.';
COMMENT ON COLUMN public.profiles.exam_date IS 'Cast from MongoDB ISO string ''YYYY-MM-DD'' via exam_date::DATE in migration script.';

CREATE TABLE IF NOT EXISTS public.subscriptions (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         TEXT        NOT NULL UNIQUE REFERENCES public.users(user_id) ON DELETE CASCADE,
    plan            TEXT        NOT NULL DEFAULT 'monthly',
    status          TEXT        NOT NULL DEFAULT 'active',
    platform        TEXT        NOT NULL DEFAULT 'mock',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,

    CONSTRAINT subscriptions_plan_check
        CHECK (plan IN ('monthly', 'annual')),
    CONSTRAINT subscriptions_status_check
        CHECK (status IN ('active', 'cancelled', 'expired'))
);

COMMENT ON TABLE  public.subscriptions IS 'One row per user. Upsert by /api/subscription/activate and /cancel.';

-- ============================================================
-- MIGRATION 004 — Learning Progress Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS public.user_word_progress (
    id                      BIGSERIAL   PRIMARY KEY,
    user_id                 TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    word_id                 TEXT        NOT NULL REFERENCES public.words(id)      ON DELETE CASCADE,
    status                  TEXT        NOT NULL DEFAULT 'NEW',
    mastery_score           NUMERIC(5,1) NOT NULL DEFAULT 0,
    confidence_score        NUMERIC(5,1) NOT NULL DEFAULT 0,
    difficulty              NUMERIC(5,3) NOT NULL DEFAULT 0,
    times_seen              INTEGER     NOT NULL DEFAULT 0,
    times_correct           INTEGER     NOT NULL DEFAULT 0,
    times_wrong             INTEGER     NOT NULL DEFAULT 0,
    consecutive_correct     INTEGER     NOT NULL DEFAULT 0,
    review_interval         INTEGER     NOT NULL DEFAULT 0,
    last_reviewed_at        TIMESTAMPTZ,
    next_review_at          TIMESTAMPTZ,
    average_response_time   INTEGER     NOT NULL DEFAULT 0,
    recent_results          SMALLINT[]  NOT NULL DEFAULT '{}',
    last_reason_codes       TEXT[]      NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ,

    CONSTRAINT uwp_user_word_unique   UNIQUE (user_id, word_id),
    CONSTRAINT uwp_status_check       CHECK (status IN ('NEW','SEEN','LEARNING','RECALLING','MASTERED')),
    CONSTRAINT uwp_mastery_range      CHECK (mastery_score    >= 0 AND mastery_score    <= 100),
    CONSTRAINT uwp_confidence_range   CHECK (confidence_score >= 0 AND confidence_score <= 100),
    CONSTRAINT uwp_difficulty_range   CHECK (difficulty >= 0 AND difficulty <= 1)
);

COMMENT ON TABLE  public.user_word_progress IS 'Adaptive learning engine state per (user, word). Upserted on every /api/practice/answer.';
COMMENT ON COLUMN public.user_word_progress.mastery_score IS '0–100. Demonstrated retention.';
COMMENT ON COLUMN public.user_word_progress.recent_results IS 'Last 10 answers: 1=correct, 0=wrong.';

CREATE TABLE IF NOT EXISTS public.saved_words (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    word_id     TEXT        NOT NULL REFERENCES public.words(id)      ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT saved_words_user_word_unique UNIQUE (user_id, word_id)
);

COMMENT ON TABLE  public.saved_words IS 'User word bookmarks. Upserted by /api/words/{word_id}/save.';

CREATE TABLE IF NOT EXISTS public.study_sessions (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    answered    INTEGER     NOT NULL DEFAULT 0,
    correct     INTEGER     NOT NULL DEFAULT 0,
    duration_ms INTEGER     NOT NULL DEFAULT 0,
    source      TEXT        NOT NULL DEFAULT 'mission',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.study_sessions IS 'Append-only practice session log. Used for streak and study-minutes.';

-- ============================================================
-- MIGRATION 005 — AI Coach & TTS Cache
-- ============================================================

CREATE TABLE IF NOT EXISTS public.ai_coach_content (
    id          BIGSERIAL   PRIMARY KEY,
    word_id     TEXT        NOT NULL UNIQUE REFERENCES public.words(id) ON DELETE CASCADE,
    content     JSONB       NOT NULL,
    provenance  TEXT        NOT NULL DEFAULT 'ai_generated',
    status      TEXT        NOT NULL DEFAULT 'PUBLISHED',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ai_coach_content_status_check
        CHECK (status IN ('DRAFT', 'REVIEW', 'PUBLISHED', 'ARCHIVED'))
);

COMMENT ON TABLE  public.ai_coach_content IS 'Cached AI Coach explanations. content = { explanation, example, mnemonic }.';

CREATE TABLE IF NOT EXISTS public.ai_coach_usage (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    word_id     TEXT        NOT NULL REFERENCES public.words(id)      ON DELETE CASCADE,
    date        DATE        NOT NULL DEFAULT CURRENT_DATE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.ai_coach_usage IS 'Daily AI Coach rate-limit log. free=3/day, pro=unlimited.';

CREATE TABLE IF NOT EXISTS public.tts_cache (
    key         TEXT        PRIMARY KEY,
    audio       BYTEA       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.tts_cache IS 'TTS audio cache. key=SHA256 hex. audio=raw mp3 BYTEA (~8–50 KB).';

-- ============================================================
-- MIGRATION 006 — Analytics Events
-- ============================================================

CREATE TABLE IF NOT EXISTS public.analytics_events (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    event       TEXT        NOT NULL,
    props       JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.analytics_events IS 'Immutable append-only event log. props is JSONB (variable payload per event type).';

-- ============================================================
-- MIGRATION 007 — Indexes, Constraints & Trigger
-- + PREFLIGHT CORRECTION: pg_trgm indexes for ILIKE search
-- ============================================================

-- ── words ────────────────────────────────────────────────────
-- Canonical key uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS words_canonical_key_unique
    ON public.words (canonical_key);

CREATE INDEX IF NOT EXISTS words_headword_idx
    ON public.words (headword);

CREATE INDEX IF NOT EXISTS words_status_idx
    ON public.words (status);

CREATE INDEX IF NOT EXISTS words_topic_idx
    ON public.words (topic);

CREATE INDEX IF NOT EXISTS words_cefr_idx
    ON public.words (cefr);

-- GIN for exam_relevance array containment
CREATE INDEX IF NOT EXISTS words_exam_relevance_gin
    ON public.words USING GIN (exam_relevance);

-- 🔧 PREFLIGHT CORRECTION: Trigram GIN indexes for ILIKE support
-- ──────────────────────────────────────────────────────────────
-- The existing FastAPI list_words() uses MongoDB $regex which is
-- equivalent to PostgreSQL ILIKE '%term%' (case-insensitive substring).
-- The tsvector index below CANNOT serve this query pattern because
-- tsvector uses English stemming — it is NOT a substring index.
-- pg_trgm GIN indexes DO support ILIKE '%term%' with index pushdown.
-- These indexes are REQUIRED for search performance in Stage 3.
-- ──────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS words_headword_trgm_idx
    ON public.words USING GIN (headword gin_trgm_ops);

CREATE INDEX IF NOT EXISTS words_definition_trgm_idx
    ON public.words USING GIN (simple_definition gin_trgm_ops);

-- tsvector GIN index (ADDITIVE — for future full-word search only,
-- NOT a replacement for the ILIKE search in list_words())
CREATE INDEX IF NOT EXISTS words_fts_idx
    ON public.words USING GIN (
        to_tsvector('english',
            COALESCE(headword, '') || ' ' ||
            COALESCE(simple_definition, ''))
    );

-- GIN for relations JSONB graph queries
CREATE INDEX IF NOT EXISTS words_relations_gin
    ON public.words USING GIN (relations);

-- ── users ────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS users_email_idx
    ON public.users (email);

CREATE INDEX IF NOT EXISTS users_tier_idx
    ON public.users (tier);

-- ── user_sessions ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS user_sessions_token_idx
    ON public.user_sessions (session_token);

CREATE INDEX IF NOT EXISTS user_sessions_user_idx
    ON public.user_sessions (user_id);

-- Expired session cleanup support (replaces MongoDB TTL index)
CREATE INDEX IF NOT EXISTS user_sessions_expires_idx
    ON public.user_sessions (expires_at);

-- ── user_word_progress ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS uwp_user_word_idx
    ON public.user_word_progress (user_id, word_id);

-- Partial index for review queue (mission selection)
CREATE INDEX IF NOT EXISTS uwp_review_queue_idx
    ON public.user_word_progress (user_id, next_review_at)
    WHERE status != 'MASTERED';

CREATE INDEX IF NOT EXISTS uwp_status_idx
    ON public.user_word_progress (user_id, status);

CREATE INDEX IF NOT EXISTS uwp_mastery_idx
    ON public.user_word_progress (user_id, mastery_score);

-- ── saved_words ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS saved_words_user_idx
    ON public.saved_words (user_id, created_at DESC);

-- ── study_sessions ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS study_sessions_user_idx
    ON public.study_sessions (user_id, created_at DESC);

-- ── analytics_events ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS analytics_user_idx
    ON public.analytics_events (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS analytics_event_idx
    ON public.analytics_events (event, created_at DESC);

CREATE INDEX IF NOT EXISTS analytics_props_gin
    ON public.analytics_events USING GIN (props);

-- ── ai_coach_usage ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ai_usage_user_date_idx
    ON public.ai_coach_usage (user_id, date);

-- ── articles ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS articles_level_idx
    ON public.articles (level);

CREATE INDEX IF NOT EXISTS articles_topic_idx
    ON public.articles (topic);

-- ── updated_at trigger ────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.set_updated_at() IS 'Sets updated_at = now() before every UPDATE.';

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

-- ============================================================
-- END OF MIGRATION
-- ============================================================
-- Expected result: 15 tables + 27 indexes + 1 trigger function
--                 + 5 triggers (one per updated_at table)
-- ============================================================
