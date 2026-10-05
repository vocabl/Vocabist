-- =============================================================================
-- Vocabist Migration 009: Semantic Search with pgvector
-- Run in Supabase SQL Editor
-- ADDITIVE ONLY — does not drop, alter, or delete any existing tables or data
-- =============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Word embeddings table
--    One embedding per word per model version. Allows future re-embedding.
CREATE TABLE IF NOT EXISTS public.word_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    word_id     TEXT NOT NULL REFERENCES public.words(id) ON DELETE CASCADE,
    embedding   vector(2048),         -- Nemotron Embed 1B produces 2048-d vectors
    embedding_model   TEXT NOT NULL DEFAULT 'nemotron-embed',
    embedding_version TEXT NOT NULL DEFAULT 'v1',
    content_hash      TEXT,           -- SHA256 prefix of the text that was embedded
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(word_id, embedding_model, embedding_version)
);

-- 3. Indexes for fast lookup and vector similarity search
CREATE INDEX IF NOT EXISTS idx_word_embeddings_word_id
    ON public.word_embeddings(word_id);

CREATE INDEX IF NOT EXISTS idx_word_embeddings_model_version
    ON public.word_embeddings(embedding_model, embedding_version);

-- IVFFlat index for approximate nearest neighbor search
-- (Only created after data exists; will be created by a separate command)
-- For now, use exact search which works on small datasets (<10k vectors)

-- 4. Embedding jobs table (admin-managed background jobs)
CREATE TABLE IF NOT EXISTS public.embedding_jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'QUEUED',
    total_words INTEGER NOT NULL DEFAULT 0,
    processed   INTEGER NOT NULL DEFAULT 0,
    successful  INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    skipped     INTEGER NOT NULL DEFAULT 0,
    embedding_model   TEXT NOT NULL DEFAULT 'nemotron-embed',
    embedding_version TEXT NOT NULL DEFAULT 'v1',
    admin_id    TEXT,
    error       TEXT,
    started_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms INTEGER
);

-- 5. Semantic search function using cosine similarity
--    Returns word IDs + similarity scores.
--    SECURITY DEFINER with empty search_path to prevent search_path hijacking.
--    All relations fully qualified to public schema.
CREATE OR REPLACE FUNCTION public.match_word_embeddings(
    query_embedding vector(2048),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 20,
    p_model TEXT DEFAULT 'nemotron-embed',
    p_version TEXT DEFAULT 'v1'
)
RETURNS TABLE (
    word_id TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    RETURN QUERY
    SELECT
        we.word_id,
        (1 - (we.embedding OPERATOR(public.<=>) query_embedding))::FLOAT AS similarity
    FROM public.word_embeddings we
    JOIN public.words w ON w.id = we.word_id AND w.status = 'PUBLISHED'
    WHERE we.embedding_model = p_model
      AND we.embedding_version = p_version
      AND (1 - (we.embedding OPERATOR(public.<=>) query_embedding)) > match_threshold
    ORDER BY we.embedding OPERATOR(public.<=>) query_embedding
    LIMIT match_count;
END;
$$;

-- 6. Function privileges
--    FastAPI backend uses service_role to call this function.
--    No direct client (student/admin browser) access to the RPC.
REVOKE EXECUTE ON FUNCTION public.match_word_embeddings FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.match_word_embeddings FROM anon;
REVOKE EXECUTE ON FUNCTION public.match_word_embeddings FROM authenticated;
GRANT  EXECUTE ON FUNCTION public.match_word_embeddings TO service_role;

-- 7. RLS policies
--    RLS enabled on both tables.
--    No broad USING(true)/WITH CHECK(true) client-access policies.
--    The FastAPI backend connects with service_role, which bypasses RLS.
--    Student and admin browser clients have zero direct table access.
ALTER TABLE public.word_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.embedding_jobs  ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- DONE.
-- No existing tables modified. No data deleted. No INSERT/UPDATE/DELETE.
-- Only additive: 2 new tables, 2 indexes, 1 function, privileges, RLS.
-- =============================================================================
