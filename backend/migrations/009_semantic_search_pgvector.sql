-- =============================================================================
-- Vocabist Migration 009: Semantic Search with pgvector
-- Run in Supabase SQL Editor
-- ADDITIVE ONLY — does not drop, alter, or delete any existing tables or data
-- =============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Word embeddings table
--    One embedding per word per model version. Allows future re-embedding.
CREATE TABLE IF NOT EXISTS word_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    word_id     TEXT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    embedding   vector(2048),         -- Nemotron Embed 1B produces 2048-d vectors
    embedding_model   TEXT NOT NULL DEFAULT 'nemotron-embed',
    embedding_version TEXT NOT NULL DEFAULT 'v1',
    content_hash      TEXT,           -- SHA256 of the text that was embedded
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(word_id, embedding_model, embedding_version)
);

-- 3. Indexes for fast lookup and vector similarity search
CREATE INDEX IF NOT EXISTS idx_word_embeddings_word_id
    ON word_embeddings(word_id);

CREATE INDEX IF NOT EXISTS idx_word_embeddings_model_version
    ON word_embeddings(embedding_model, embedding_version);

-- IVFFlat index for approximate nearest neighbor search
-- (Only created after data exists; will be created by a separate command)
-- For now, use exact search which works on small datasets (<10k vectors)

-- 4. Embedding jobs table (admin-managed background jobs)
CREATE TABLE IF NOT EXISTS embedding_jobs (
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
--    Returns word IDs + similarity scores
CREATE OR REPLACE FUNCTION match_word_embeddings(
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
AS $$
BEGIN
    RETURN QUERY
    SELECT
        we.word_id,
        1 - (we.embedding <=> query_embedding) AS similarity
    FROM word_embeddings we
    JOIN words w ON w.id = we.word_id AND w.status = 'PUBLISHED'
    WHERE we.embedding_model = p_model
      AND we.embedding_version = p_version
      AND 1 - (we.embedding <=> query_embedding) > match_threshold
    ORDER BY we.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. RLS policies
ALTER TABLE word_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE embedding_jobs ENABLE ROW LEVEL SECURITY;

-- Service role can do everything (backend uses service_role key)
CREATE POLICY "service_role_word_embeddings" ON word_embeddings
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "service_role_embedding_jobs" ON embedding_jobs
    FOR ALL USING (true) WITH CHECK (true);

-- Anonymous/authenticated users: read-only access to embeddings
-- (needed for the semantic search RPC which uses SECURITY DEFINER)
-- The actual search is done via the RPC function above.

-- 7. Grant execute on the search function
GRANT EXECUTE ON FUNCTION match_word_embeddings TO authenticated;
GRANT EXECUTE ON FUNCTION match_word_embeddings TO anon;
GRANT EXECUTE ON FUNCTION match_word_embeddings TO service_role;

-- =============================================================================
-- DONE. No existing tables modified. No data deleted.
-- =============================================================================
