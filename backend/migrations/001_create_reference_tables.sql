-- ============================================================
-- MIGRATION 001: Reference / Lookup Tables
-- Project  : Vocabist → Supabase
-- Purpose  : Create static reference tables that all other
--            tables depend on (topics, exams, articles).
-- Safety   : Non-destructive. Uses CREATE TABLE IF NOT EXISTS.
-- Run via  : Supabase Dashboard → SQL Editor
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 001a. topics
--   MongoDB: db.topics  (6 docs)
--   Slug is the canonical reference key used by words.topic
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.topics (
    slug        TEXT        PRIMARY KEY,           -- 'academic', 'everyday', …
    name        TEXT        NOT NULL,
    icon        TEXT,                              -- Ionicons name string
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.topics IS 'Vocabulary topic taxonomy. Slug is the stable FK used by words.topic.';
COMMENT ON COLUMN public.topics.slug IS 'Unique machine-readable key. Matches words.topic.';

-- ────────────────────────────────────────────────────────────
-- 001b. exams
--   MongoDB: db.exams  (6 docs)
--   Slug is the canonical reference used by words.exam_relevance[]
--   and profiles.exam_slug.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.exams (
    slug        TEXT        PRIMARY KEY,           -- 'ielts', 'gre', 'sat', …
    name        TEXT        NOT NULL,
    full_name   TEXT,
    category    TEXT,                              -- 'study_abroad', 'grad_school', …
    score_type  TEXT,                              -- 'band', 'points', 'level'
    max_score   NUMERIC(6,1),
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.exams IS 'Supported exam list. Slug is the stable FK used by words.exam_relevance[] and profiles.exam_slug.';
COMMENT ON COLUMN public.exams.max_score IS 'E.g. 9.0 for IELTS, 120 for TOEFL, 340 for GRE.';

-- ────────────────────────────────────────────────────────────
-- 001c. articles
--   MongoDB: db.articles  (4 docs)
--   Used by the Read & Learn feature.
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.articles (
    id          TEXT        PRIMARY KEY,           -- e.g. 'morning-routines'
    title       TEXT        NOT NULL,
    level       TEXT,                              -- CEFR level: A1–C2
    topic       TEXT        REFERENCES public.topics(slug) ON DELETE SET NULL,
    minutes     INTEGER,                           -- estimated reading time
    excerpt     TEXT,
    body        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.articles IS 'Short reading articles for the Read & Learn feature.';
COMMENT ON COLUMN public.articles.level IS 'CEFR reading level: A1, A2, B1, B2, C1, C2.';
COMMENT ON COLUMN public.articles.topic IS 'FK to topics.slug. NULL if topic is deleted.';
