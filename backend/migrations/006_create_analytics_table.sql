-- ============================================================
-- MIGRATION 006: Analytics Events Table
-- Project  : Vocabist → Supabase
-- Purpose  : Append-only event log for user behavior
--            analytics.
-- Safety   : Non-destructive. Uses CREATE TABLE IF NOT EXISTS.
-- Depends  : Migration 003 (users)
-- Run via  : Supabase Dashboard → SQL Editor
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 006a. analytics_events
--   MongoDB: db.analytics_events  (63 docs at audit time)
--
--   Immutable append-only event log. props is completely
--   flexible (different keys per event type) → JSONB.
--
--   Known event types (from server.py at audit time):
--     onboarding_completed      { reason, level }
--     word_viewed               { word_id }
--     word_saved                { word_id }
--     word_mastered             { word_id }
--     answer_submitted          { word_id, correct, mode }
--     learning_session_started  { source, count }
--     learning_session_completed{ answered, correct, source }
--     ai_coach_generated        { word_id }
--     subscription_started      { plan }
--     subscription_cancelled    {}
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.analytics_events (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    event       TEXT        NOT NULL,
    -- Event name e.g. 'word_mastered', 'answer_submitted'

    props       JSONB       NOT NULL DEFAULT '{}',
    -- Completely flexible event payload. Examples:
    --   answer_submitted:           { word_id, correct, mode }
    --   learning_session_completed: { answered, correct, source }
    --   ai_coach_generated:         { word_id }
    --   subscription_started:       { plan }

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.analytics_events IS 'Immutable append-only event log. props is JSONB because each event type has a different payload shape.';
COMMENT ON COLUMN public.analytics_events.event IS 'Event name. See migration header for known types.';
COMMENT ON COLUMN public.analytics_events.props IS 'JSONB event payload. Shape varies by event type.';
