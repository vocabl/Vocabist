-- ============================================================
-- MIGRATION 008: Add source_mongo_id to append-only tables
-- Project  : Vocabist → Supabase
-- Purpose  : Intrinsic idempotency for the three collections
--            that have BIGSERIAL PKs and no natural unique key:
--              - study_sessions
--              - ai_coach_usage
--              - analytics_events
--
-- WHY THIS IS NEEDED:
--   These tables use surrogate BIGSERIAL PKs with no business-
--   level unique key. Without this column, the only duplicate
--   protection during migration is migration_state.json, which
--   can be deleted or bypassed if the process crashes mid-batch.
--
--   Adding source_mongo_id TEXT UNIQUE means:
--     - Every migrated document carries its original MongoDB
--       ObjectId as a 24-char hex string.
--     - INSERT ON CONFLICT (source_mongo_id) DO NOTHING is the
--       dedup mechanism, independent of any state file.
--     - New records created natively in Supabase (post-migration)
--       have source_mongo_id = NULL — multiple NULLs are allowed
--       by PostgreSQL UNIQUE indexes (NULL ≠ NULL).
--     - Re-running the migration N times is always safe.
--
-- SAFETY:
--   ✅ ADD COLUMN IF NOT EXISTS — safe to re-run
--   ✅ CREATE UNIQUE INDEX IF NOT EXISTS — safe to re-run
--   ✅ No DROP, TRUNCATE, DELETE
--   ✅ No data modification
--   ✅ Backward compatible: existing application code is
--      unaffected (source_mongo_id is NULL for new records)
--
-- RUN VIA: Supabase Dashboard → SQL Editor
--          (Direct PostgreSQL port 5432 blocked in this env)
-- ============================================================

-- ── study_sessions ───────────────────────────────────────────
ALTER TABLE public.study_sessions
    ADD COLUMN IF NOT EXISTS source_mongo_id TEXT;

COMMENT ON COLUMN public.study_sessions.source_mongo_id IS
    'MongoDB ObjectId hex string of the source document. '
    'NULL for records created natively in Supabase post-migration. '
    'UNIQUE ensures the migration cannot insert duplicates even on retry.';

CREATE UNIQUE INDEX IF NOT EXISTS study_sessions_source_mongo_id_unique
    ON public.study_sessions (source_mongo_id)
    WHERE source_mongo_id IS NOT NULL;

-- ── ai_coach_usage ────────────────────────────────────────────
ALTER TABLE public.ai_coach_usage
    ADD COLUMN IF NOT EXISTS source_mongo_id TEXT;

COMMENT ON COLUMN public.ai_coach_usage.source_mongo_id IS
    'MongoDB ObjectId hex string of the source document. '
    'NULL for records created natively in Supabase post-migration. '
    'UNIQUE ensures the migration cannot insert duplicates even on retry.';

CREATE UNIQUE INDEX IF NOT EXISTS ai_coach_usage_source_mongo_id_unique
    ON public.ai_coach_usage (source_mongo_id)
    WHERE source_mongo_id IS NOT NULL;

-- ── analytics_events ──────────────────────────────────────────
ALTER TABLE public.analytics_events
    ADD COLUMN IF NOT EXISTS source_mongo_id TEXT;

COMMENT ON COLUMN public.analytics_events.source_mongo_id IS
    'MongoDB ObjectId hex string of the source document. '
    'NULL for records created natively in Supabase post-migration. '
    'UNIQUE ensures the migration cannot insert duplicates even on retry.';

CREATE UNIQUE INDEX IF NOT EXISTS analytics_events_source_mongo_id_unique
    ON public.analytics_events (source_mongo_id)
    WHERE source_mongo_id IS NOT NULL;

-- ============================================================
-- VERIFICATION QUERY (run after applying this migration):
-- ============================================================
-- SELECT table_name, column_name, is_nullable, data_type
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND column_name = 'source_mongo_id'
-- ORDER BY table_name;
--
-- Expected output:
--   ai_coach_usage    | source_mongo_id | YES | text
--   analytics_events  | source_mongo_id | YES | text
--   study_sessions    | source_mongo_id | YES | text
-- ============================================================
