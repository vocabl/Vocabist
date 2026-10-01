-- ============================================================
-- MIGRATION 003: User & Auth Tables
-- Project  : Vocabist → Supabase
-- Purpose  : Create user identity, session, profile and
--            subscription tables.
-- Safety   : Non-destructive. Uses CREATE TABLE IF NOT EXISTS.
-- Depends  : Migration 001 (exams slug referenced by profiles)
-- Run via  : Supabase Dashboard → SQL Editor
--
-- NOTE ON AUTH:
--   The existing auth system uses custom user_id strings
--   (format: "user_" + 6-byte hex) and a custom session table
--   (Bearer tokens, 7-day TTL). This schema intentionally
--   keeps the custom auth tables separate from Supabase Auth
--   (auth.users) to allow a phased auth migration in a future
--   stage without disrupting active sessions.
--   DO NOT merge with auth.users until explicitly approved.
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 003a. users
--   MongoDB: db.users  (16 docs at audit time)
--
--   user_id is the stable application-level identity string.
--   password_hash is nullable (NULL for Google OAuth users).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
    user_id         TEXT        PRIMARY KEY,
    -- Format: "user_" + secrets.token_hex(6), e.g. "user_a1b2c3d4e5f6"

    email           TEXT        NOT NULL,
    name            TEXT,
    picture         TEXT,                          -- avatar URL (Google or NULL)
    password_hash   TEXT,                          -- NULL for OAuth-only accounts

    onboarded       BOOLEAN     NOT NULL DEFAULT FALSE,
    tier            TEXT        NOT NULL DEFAULT 'free',
    -- 'free' | 'pro'

    xp              INTEGER     NOT NULL DEFAULT 0,
    streak          INTEGER     NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,

    CONSTRAINT users_email_unique UNIQUE (email),
    CONSTRAINT users_tier_check   CHECK (tier IN ('free', 'pro'))
);

COMMENT ON TABLE  public.users IS 'Application user accounts. user_id is the stable app-level identity (NOT Supabase auth.users.id). Auth migration is a separate future phase.';
COMMENT ON COLUMN public.users.user_id IS 'Custom string PK: "user_" + 6-byte hex. Stable across all migrations.';
COMMENT ON COLUMN public.users.password_hash IS 'bcrypt hash. NULL for Google-OAuth users.';
COMMENT ON COLUMN public.users.tier IS 'Entitlement tier: free | pro.';

-- ────────────────────────────────────────────────────────────
-- 003b. user_sessions
--   MongoDB: db.user_sessions  (17 docs at audit time)
--
--   Bearer token sessions (7-day TTL). MongoDB TTL index on
--   expires_at is replaced by a periodic purge query in
--   PostgreSQL:
--     DELETE FROM user_sessions WHERE expires_at < now();
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_sessions (
    id              BIGSERIAL   PRIMARY KEY,
    session_token   TEXT        NOT NULL UNIQUE,
    user_id         TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE  public.user_sessions IS 'Bearer token sessions. Rows with expires_at < now() are expired. Purge: DELETE FROM user_sessions WHERE expires_at < now();';
COMMENT ON COLUMN public.user_sessions.session_token IS 'URL-safe random 32-byte token (secrets.token_urlsafe(32)).';

-- ────────────────────────────────────────────────────────────
-- 003c. profiles
--   MongoDB: db.profiles  (11 docs at audit time)
--
--   One profile per user. Created lazily on first access.
--   Stores onboarding answers, learning goals and streak/XP
--   (duplicated from users for query convenience).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
    user_id         TEXT        PRIMARY KEY REFERENCES public.users(user_id) ON DELETE CASCADE,

    -- onboarding answers
    reason          TEXT,                          -- e.g. 'IELTS', 'career', 'general'
    level           TEXT,                          -- CEFR self-assessment: A1–C2
    daily_minutes   INTEGER     NOT NULL DEFAULT 10,

    -- exam goal
    exam_slug       TEXT        REFERENCES public.exams(slug) ON DELETE SET NULL,
    exam_date       DATE,                          -- ISO date stored as DATE
    target_score    NUMERIC(6,2),

    -- gamification (kept in sync with users.streak / users.xp)
    streak          INTEGER     NOT NULL DEFAULT 0,
    longest_streak  INTEGER     NOT NULL DEFAULT 0,
    xp              INTEGER     NOT NULL DEFAULT 0,
    last_active_date DATE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

COMMENT ON TABLE  public.profiles IS 'One-to-one extension of users. Onboarding answers, exam goals, streak and XP mirror.';
COMMENT ON COLUMN public.profiles.exam_date IS 'Stored as DATE (was ISO string in MongoDB).';
COMMENT ON COLUMN public.profiles.level IS 'CEFR self-assessed level. Not the same as words.cefr.';

-- ────────────────────────────────────────────────────────────
-- 003d. subscriptions
--   MongoDB: db.subscriptions  (2 docs at audit time)
--
--   One subscription record per user (upsert pattern).
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         TEXT        NOT NULL UNIQUE REFERENCES public.users(user_id) ON DELETE CASCADE,
    plan            TEXT        NOT NULL DEFAULT 'monthly',
    -- 'monthly' | 'annual'
    status          TEXT        NOT NULL DEFAULT 'active',
    -- 'active' | 'cancelled' | 'expired'
    platform        TEXT        NOT NULL DEFAULT 'mock',
    -- 'mock' | 'ios' | 'android' | 'stripe'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,

    CONSTRAINT subscriptions_plan_check
        CHECK (plan IN ('monthly', 'annual')),
    CONSTRAINT subscriptions_status_check
        CHECK (status IN ('active', 'cancelled', 'expired'))
);

COMMENT ON TABLE  public.subscriptions IS 'One row per user. Upsert-maintained by /api/subscription/activate and /cancel.';
COMMENT ON COLUMN public.subscriptions.platform IS 'Payment platform: mock (dev) | ios | android | stripe.';
