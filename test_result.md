# Vocabist AI Platform P2 — Test Results

## Test Credentials
- **Student Account**: `test@vocabist.com` / `test1234`
- **Admin Account**: `imsunil0202@gmail.com` (password not known to agent; admin only via ADMIN_EMAILS env)

## Features Implemented

### 1. Semantic Search (Hybrid)
- **Endpoint**: `GET /api/search/hybrid?q=...`
- Combines exact text search + semantic embedding search
- Falls back gracefully when pgvector/embeddings not available
- Debounced in frontend, exact results shown immediately

### 2. Visual Capture
- **Endpoints**: `POST /api/visual-capture/extract`, `POST /api/visual-capture/import`
- Upload image → Muse Glimmer → structured vocabulary extraction
- Deduplication against existing words
- All candidates enter REVIEW (never auto-published)
- Camera permissions declared in app.json

### 3. Bulk Vocabulary Generation
- **Endpoints**: `POST /api/admin/vocabulary/bulk-generate`, `POST /api/admin/vocabulary/bulk-approve`, `POST /api/admin/vocabulary/bulk-reject`
- Full config: CEFR, Topic, POS, Exam, Vocabulary Type, Quality, Enrichment
- Confirmation required for >50 words
- Max 500 words per job
- Guided Review Queue with select mode, bulk approve/reject

### 4. Model Insights
- **Endpoint**: `GET /api/admin/ai/insights?days=30&model=...&task=...`
- Per-model metrics: requests, success/failure rate, avg/p50/p95 latency
- Token usage where available
- Cost shown only when reliable (shows "Unavailable" otherwise)
- Task breakdown with model filtering
- Model comparison view

### 5. Embedding Management (Admin)
- **Endpoints**: `GET /api/admin/embeddings/status`, `POST /api/admin/embeddings/jobs`, `GET /api/admin/embeddings/jobs`
- Generate missing, regenerate stale, regenerate all
- Job progress tracking
- Coverage statistics

## Supabase SQL Migration Required
File: `/app/backend/migrations/009_semantic_search_pgvector.sql`
- Enables pgvector extension
- Creates `word_embeddings` table (2048-d vectors)
- Creates `embedding_jobs` table
- Creates `match_word_embeddings` RPC function
- RLS enabled with service_role policies
- MUST be run by user in Supabase SQL Editor before semantic search works

## Backend Port: 8001
## Frontend Port: 3000
