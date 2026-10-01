# Vocabist — Supabase SQL Migrations

## Overview

These versioned SQL files define the complete PostgreSQL schema for the Vocabist
application, designed to faithfully represent the existing MongoDB data model.

**Current status:** Schema design complete. Data migration NOT yet started.
**Active database:** MongoDB (unchanged). Supabase is the migration target.

---

## File Order (run in sequence)

| File | Tables Created | MongoDB Source |
|------|---------------|----------------|
| `001_create_reference_tables.sql` | topics, exams, articles | db.topics (6), db.exams (6), db.articles (4) |
| `002_create_word_tables.sql` | words | db.words (231) |
| `003_create_user_tables.sql` | users, user_sessions, profiles, subscriptions | db.users (16), db.user_sessions (17), db.profiles (11), db.subscriptions (2) |
| `004_create_progress_tables.sql` | user_word_progress, saved_words, study_sessions | db.user_word_progress (7), db.saved_words (2), db.study_sessions (3) |
| `005_create_ai_and_tts_tables.sql` | ai_coach_content, ai_coach_usage, tts_cache | db.ai_coach_content (4), db.ai_coach_usage (4), db.tts_cache (1) |
| `006_create_analytics_table.sql` | analytics_events | db.analytics_events (63) |
| `007_create_indexes_and_constraints.sql` | All indexes + updated_at trigger | — |

---

## How to Run

### Option A — Supabase Dashboard (Recommended for this environment)

1. Open your project at https://app.supabase.com
2. Navigate to **SQL Editor** (left sidebar)
3. Open each file in numbered order (001 → 007)
4. Click **Run** for each file
5. Verify the output panel shows no errors

### Option B — psql (if direct DB access is available outside Kubernetes)

```bash
# The SUPABASE_DB_URL password contains @ and must be URL-encoded
export DB_URL="postgresql://postgres:12354%40Solana@db.selgftsufpxvehumckmw.supabase.co:5432/postgres"

for n in 001 002 003 004 005 006 007; do
  echo "Running migration ${n}..."
  psql "$DB_URL" -f ${n}_*.sql
done
```

---

## Safety Guarantees

- Every `CREATE TABLE` uses `IF NOT EXISTS` — safe to re-run
- Every `CREATE INDEX` uses `IF NOT EXISTS` — safe to re-run
- No `DROP`, `TRUNCATE`, or `DELETE` statements anywhere
- No data modification (INSERT/UPDATE) in any migration file
- Foreign keys reference only stable natural PKs (no UUIDs invented)

---

## SUPABASE_DB_URL Note

The password contains `@` which must be URL-encoded as `%40` when using psycopg2:

```python
import urllib.parse
password = "12354@Solana"
encoded  = urllib.parse.quote(password, safe="")
url = f"postgresql://postgres:{encoded}@db.selgftsufpxvehumckmw.supabase.co:5432/postgres"
```

---

## Connectivity Summary (from this Kubernetes environment)

| Method | Status | Notes |
|--------|--------|-------|
| Supabase REST API (HTTPS/443) | ✅ CONNECTED | Primary method for all app data operations |
| Supabase Pooler host (TCP) | ✅ HOST RESOLVES | Auth error indicates password issue; use Dashboard |
| Direct DB host (port 5432) | ❌ DNS BLOCKED | Kubernetes network policy; use Dashboard SQL Editor |

---

## Pending Stages (DO NOT START until each is approved)

- **Stage 2:** Data migration scripts (MongoDB → Supabase COPY)
- **Stage 3:** Dual-write / application code switchover
- **Stage 4:** Auth migration (custom sessions → Supabase Auth)
- **Stage 5:** MongoDB decommission
