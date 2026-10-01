-- ============================================================
-- MIGRATION 002: Vocabulary / Word Tables
-- Project  : Vocabist → Supabase
-- Purpose  : Create the canonical words table, the central
--            table for the entire Vocabist vocabulary engine.
-- Safety   : Non-destructive. Uses CREATE TABLE IF NOT EXISTS.
-- Depends  : Migration 001 (topics must exist)
-- Run via  : Supabase Dashboard → SQL Editor
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 002a. words
--   MongoDB: db.words  (231 docs at audit time)
--
--   Column strategy
--   ───────────────
--   COLUMNS  → all scalar fields that are filtered, sorted,
--              or joined (id, cefr, topic, status, provenance,
--              scores, flat legacy arrays).
--   TEXT[]   → small arrays of simple strings that need GIN
--              filtering (exam_relevance, synonyms, antonyms,
--              related, word_family, roots, prefixes, suffixes,
--              confusing_words).
--   JSONB    → genuinely nested/structured objects where
--              individual sub-keys are NOT independently
--              queried at the DB level (meanings, pronunciation,
--              relations canonical graph, audio URLs,
--              translations, contextual_examples,
--              school_relevance).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.words (

    -- ── Identity ──────────────────────────────────────────
    id                  TEXT        PRIMARY KEY,
    -- Slug-based stable ID, e.g. 'abate', 'ubiquitous'.
    -- Matches MongoDB words.id and is used as FK everywhere.

    headword            TEXT        NOT NULL,
    canonical_key       TEXT        NOT NULL,
    -- Normalised lowercase headword: normalize_headword(headword).
    -- Must be globally unique after backfill.

    -- ── Core vocabulary metadata ───────────────────────────
    part_of_speech      TEXT,                              -- noun/verb/adjective/adverb/…
    cefr                TEXT,                              -- A1/A2/B1/B2/C1/C2
    frequency           SMALLINT,                         -- 1 (rare) – 5 (very common)
    academic_importance SMALLINT,                         -- 1–5

    topic               TEXT        REFERENCES public.topics(slug) ON DELETE SET NULL,

    -- ── Definitions ────────────────────────────────────────
    simple_definition   TEXT,
    easy_meaning        TEXT,
    detailed_definition TEXT,
    example             TEXT,
    easy_example        TEXT,
    mnemonic            TEXT,
    common_mistakes     TEXT,
    usage_notes         TEXT,

    -- ── Phonetics (flat legacy; canonical version in pronunciation JSONB) ─
    phonetic            TEXT,                              -- primary IPA string
    phonetic_us         TEXT,
    phonetic_uk         TEXT,

    -- ── Flat legacy relation arrays (plain strings) ────────
    -- Kept for backward compatibility. Canonical relation refs
    -- with resolved word IDs live in relations JSONB below.
    synonyms            TEXT[]      NOT NULL DEFAULT '{}',
    antonyms            TEXT[]      NOT NULL DEFAULT '{}',
    related             TEXT[]      NOT NULL DEFAULT '{}',
    confusing_words     TEXT[]      NOT NULL DEFAULT '{}',
    word_family         TEXT[]      NOT NULL DEFAULT '{}',
    roots               TEXT[]      NOT NULL DEFAULT '{}',
    prefixes            TEXT[]      NOT NULL DEFAULT '{}',
    suffixes            TEXT[]      NOT NULL DEFAULT '{}',

    -- ── Exam & school relevance ────────────────────────────
    exam_relevance      TEXT[]      NOT NULL DEFAULT '{}',
    -- Array of exam slugs. GIN indexed for: WHERE 'gre' = ANY(exam_relevance)
    -- or: WHERE exam_relevance @> ARRAY['gre']

    -- ── Structured / nested fields (JSONB) ────────────────
    meanings            JSONB,
    -- Array of meaning objects:
    -- [{ part_of_speech, definition, easy_definition,
    --    detailed_definition, examples[], cefr }]

    pronunciation       JSONB,
    -- { us: { ipa, audio }, uk: { ipa, audio } }

    relations           JSONB,
    -- Canonical relation graph with resolved word IDs:
    -- { synonyms: [{ref, headword}], antonyms: [{ref, headword}],
    --   related: [{ref, headword}], confusing_words: [{ref, headword}],
    --   word_family: [str], roots: [str], prefixes: [str], suffixes: [str] }

    audio               JSONB,
    -- { us_url, uk_url, tts_url }
    -- Cached after first lookup from Free Dictionary API or TTS.

    translations        JSONB,
    -- { language_code: translated_text }, e.g. { "es": "disminuir" }

    contextual_examples JSONB,
    -- Array of { context: str, example: str }

    school_relevance    JSONB,
    -- Flexible array; structure TBD by content team

    -- ── Content lifecycle ──────────────────────────────────
    status              TEXT        NOT NULL DEFAULT 'PUBLISHED',
    -- DRAFT | REVIEW | PUBLISHED | ARCHIVED

    provenance          TEXT        NOT NULL DEFAULT 'CURATED',
    -- CURATED | AI_GENERATED | IMPORTED | ADMIN_CREATED | SEED

    provenance_original TEXT,
    -- Preserved original provenance string before standardisation

    lifecycle_version   SMALLINT    NOT NULL DEFAULT 1,
    schema_version      SMALLINT    NOT NULL DEFAULT 1,

    -- ── Timestamps ────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,

    -- ── Constraints ────────────────────────────────────────
    CONSTRAINT words_status_check
        CHECK (status IN ('DRAFT', 'REVIEW', 'PUBLISHED', 'ARCHIVED')),

    CONSTRAINT words_cefr_check
        CHECK (cefr IS NULL OR cefr IN ('A1','A2','B1','B2','C1','C2')),

    CONSTRAINT words_provenance_check
        CHECK (provenance IN ('CURATED','AI_GENERATED','IMPORTED','ADMIN_CREATED','SEED'))
);

COMMENT ON TABLE  public.words IS 'Canonical vocabulary table. id is the stable slug-based PK. canonical_key is the normalised uniqueness key.';
COMMENT ON COLUMN public.words.id IS 'Slug-based canonical word ID, e.g. "abate". Stable across migrations.';
COMMENT ON COLUMN public.words.canonical_key IS 'Lower-cased, whitespace-collapsed headword. Unique index enforced in migration 007.';
COMMENT ON COLUMN public.words.exam_relevance IS 'Array of exam slugs. GIN indexed. Query: WHERE exam_relevance @> ARRAY[''gre'']';
COMMENT ON COLUMN public.words.meanings IS 'Structured meanings array. Not individually queried at DB level → JSONB.';
COMMENT ON COLUMN public.words.relations IS 'Canonical relationship graph with resolved word IDs.';
COMMENT ON COLUMN public.words.audio IS 'Cached audio URLs: us_url, uk_url, tts_url.';
COMMENT ON COLUMN public.words.translations IS 'Translations keyed by language code, e.g. {"es": "..."}';
COMMENT ON COLUMN public.words.status IS 'Content lifecycle: DRAFT | REVIEW | PUBLISHED | ARCHIVED';
COMMENT ON COLUMN public.words.provenance IS 'Content origin: CURATED | AI_GENERATED | IMPORTED | ADMIN_CREATED | SEED';
