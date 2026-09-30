# Vocabist — Product Requirements Document

## Original Problem Statement
Build a production-quality, mobile-first English vocabulary learning platform for school
students, English learners, and competitive-exam/test-prep students worldwide. Core loop:
DISCOVER → UNDERSTAND → RECALL → USE → REVIEW → MASTER. Personalized journeys based on
level, goals, exams, study time, performance, mistakes, review history and mastery.

## Platform / Architecture
- Frontend: Expo (React Native) + TypeScript, expo-router, @tanstack/react-query.
- Backend: FastAPI + MongoDB (Motor). Opaque Bearer session tokens (7-day, TTL index).
- Auth: Email/password (bcrypt) + Emergent-managed Google OAuth.
- AI: planned via GPT-5.6 Luna through Emergent Universal key (Phase 5).
- Theme: warm light "premium education" (Sage green accent), Plus Jakarta Sans, Phosphor-style MDI icons.

## User Personas
- School student building curriculum vocabulary.
- Test-prep student (IELTS/TOEFL/GRE/SAT/GMAT) with an exam date and target.
- General English learner (CEFR A1–C2) improving everyday/academic vocabulary.

## Core Requirements (static)
- Personalized daily mission; adaptive spaced review; multi-mode practice.
- Structured (normalized) word metadata + knowledge graph relations.
- Progress, streaks, XP, achievements; entitlement (free/pro) foundation.
- Fast, calm, uncluttered UX; loading/empty/error states everywhere.

## Implemented (2026-09-29)
- **Phase 1 — Foundation:** Auth (email + Google), root auth gate, bottom tabs (Home/Learn/Exams/Discover/Profile), design system (theme tokens, Button/Card/Chip/Input/Icon/ProgressRing/Skeleton/Toast/CefrBadge), Mongo schema + indexes, seed content (20 words, 6 topics, 6 exams), user profile.
- **Phase 2 — Vocabulary engine:** Word list with search + CEFR/topic/exam filters + pagination, Word detail page with knowledge graph (synonyms/antonyms/related), save/unsave, saved list, daily mission generator.
- **Phase 3 — Practice + review:** Session player (teach card + multiple_choice / synonym / true_false / spelling / fill_blank), deterministic SM-2-style adaptive review (mastery/confidence/next_review/status NEW→SEEN→LEARNING→RECALLING→MASTERED), XP + streak, Progress screen (learned/mastered/accuracy/level/weak areas), achievements.
- **Exam Hub (partial):** exam list, exam detail with countdown/target/words-per-day/mastery progress, set-as-goal, exam-scoped practice.
- **Analytics events** logged server-side (onboarding, session start/complete, word viewed/saved, answer submitted, word mastered).

## Iteration 2 (2026-09-29)
- **Bigger Word Bank:** expanded to ~230 words (20 curated + ~210 AI-generated & validated, provenance `ai_generated`, PUBLISHED) across CEFR A1–C2, topics and exams; synonym/antonym/related chips are always tappable (open the word if it exists, else jump to Discover search).
- **AI Coach:** `POST /api/words/{id}/ai-coach` (gpt-5.6-luna) returns validated `{explanation, example, mnemonic}`, cached per word, never overwrites canonical content; surfaced on the Word Detail page.
- **Pronounce It:** `GET /api/words/{id}/audio` (Free Dictionary API US/UK + OpenAI TTS fallback), served via `GET /api/tts/{key}.mp3`; Listen + US/UK controls using expo-audio.
- **Go Pro:** centralized entitlements (free caps: 8 new words/day, 3 AI Coach/day, GRE & GMAT Pro-locked), paywall screen, `POST /api/subscription/activate|cancel`, `GET /api/entitlements`. (Mock purchase in preview; real IAP/RevenueCat at launch.)

## Iteration 3 (2026-09-29)
- **Read & Learn:** seeded articles (`/api/articles`), reader with tap-any-word bottom sheet (meaning + Listen + Save). `/api/lookup` resolves bank words, else AI-defines (dictionary API blocked in env → gpt-5.6-luna fallback).
- **Learn From Anything:** `/api/extract` (pasted text) and `/api/extract-pdf` (PDF upload via pypdf) classify vocabulary KNOWN/LEARNING/NEW; selected new words start a session via `source=list` (imports non-bank words on the fly).
- **Smart Review Nudges:** `/api/review/slipping` surfaces words due/overdue with low mastery; Home "Slipping from memory" card starts `source=slipping` review. Review engine now promotes any attempted word out of NEW → SEEN so first-wrong words are nudged.

## Phase A — Canonical Vocabulary Architecture (2026-09-30)
- **Canonical identity:** every word now has a `canonical_key` (normalized headword) with a **unique index** preventing duplicate canonical words; existing `id`/`headword` and all legacy fields preserved unchanged.
- **Schema module** `backend/vocab_schema.py` (pure, DB-free, Postgres-portable): `normalize_headword`, `canonical_id`, `build_relations`, `build_meanings`, `build_pronunciation`, `to_canonical_storage`, `new_canonical_word`.
- **Canonical relations:** embedded `relations` block resolves synonyms/antonyms/related/confusing_words to canonical word **refs** (`{ref, headword}`) instead of bare strings; morphological lists (word_family/roots/prefixes/suffixes) kept as strings. `/api/words/{id}` graph now uses refs (headword fallback) — same response shape, additive `confusing_words`.
- **Capability fields (additive):** `meanings[]` (multi-meaning/POS), `pronunciation{us,uk}` (IPA+audio), `translations`, `school_relevance`, `contextual_examples` placeholders; legacy flat fields (`simple_definition`, `phonetic`, `synonyms[]`…) untouched so all consumers keep working.
- **Idempotent backfill** `migrate_canonical()` at startup upgraded all 231 words to `schema_version:1`; `ensure_word`/import dedupe by `canonical_key`.
- Tests: `backend/tests/test_canonical_vocab.py` (schema unit tests + API canonical identity / ref resolution / duplicate prevention / no-regression). No frontend/UI changes.

## Phase B — Content Ingestion & Validation Pipeline (2026-09-30)
- **Standardized provenance:** `CURATED / AI_GENERATED / IMPORTED / ADMIN_CREATED`. Idempotent `migrate_content_lifecycle()` mapped legacy values (seed→CURATED 20, ai_generated→AI_GENERATED 210, imported→IMPORTED 1), preserving originals in `provenance_original`.
- **Content lifecycle:** `DRAFT / REVIEW / PUBLISHED / ARCHIVED` on the existing `status` field. All 231 existing words stay PUBLISHED (never downgraded) so the live app is unchanged; new AI content enters REVIEW and is excluded by the existing `{status:"PUBLISHED"}` filters. Added `lifecycle_version:1` guard.
- **Validation module** `backend/content_validation.py` (pure, DB-free, Postgres-portable): `validate_word()` → `ValidationResult{valid,errors,warnings,normalized_data}`. Errors block publication; warnings allow REVIEW. Checks identity/canonical_key/duplicates, definitions, meanings/pronunciation structure, CEFR (A1–C2), relations (self-ref, malformed, duplicate, broken ref), exam refs (verified against real exams; never invents), provenance/status/metadata.
- **Ingestion service** `backend/content_ingest.py`: `ingest_word` (normalize→canonical_key→dedupe→validate→persist-when-permitted; never overwrites trusted content), `bulk_ingest` (deterministic, idempotent, per-record results, no partial corruption), `resolve_status` (AI_GENERATED→REVIEW always; IMPORTED→PUBLISHED to preserve import behavior; CURATED/ADMIN warnings downgrade PUBLISHED→REVIEW), `quality_report`, `migrate_content_lifecycle`.
- **`/api/words/import`** now routes through `ingest_word` (IMPORTED) — same behavior: existing→returns canonical id, new+defined→PUBLISHED; dedupe by canonical_key.
- **Dev tooling:** `backend/content_report.py` read-only quality pass (found 4 pre-existing AI-bank SELF_REFERENCE issues; left untouched per spec).
- Tests: `backend/tests/test_content_pipeline.py` (validation units + async ingestion + API no-regression). No UI/engine/schema-breaking changes.

## Phase C — Knowledge Graph + Relationship Integrity (2026-09-30)
- **Reusable graph module** `backend/graph_service.py` (pure logic DB-free where practical; minimal Motor coupling): normalization, integrity, one-hop graph, migration, targeted re-resolution, metrics.
- **Canonical relationship model:** every relation entry resolves to `{ref: <canonical id|null>, headword}`. Resolution priority: valid existing `ref` → `canonical_key` from headword → normalized-headword lookup → `null`. Handles legacy strings/objects/ids. Never invents IDs.
- **Integrity rules** (`check_relationship_integrity` → `{valid, errors, warnings, normalized_relations}`): self-reference removed/flagged; duplicate targets within a type removed deterministically (first kept); malformed entries flagged; unknown relation types flagged; unresolved refs kept as `ref:null` but detectable; same target across different relation types allowed; case/whitespace normalized. Morphological fields (word_family/roots/prefixes/suffixes) preserved verbatim.
- **Repair migration** `resolve_all_relationship_refs()` (idempotent, startup + callable): normalized all words; writes only the `relations` field when it changes; never alters word IDs, definitions, CEFR, pronunciation, provenance, lifecycle status, user progress, saved words, sessions, analytics. Repaired the 4 historical AI self-references (`order/schedule/encounter/postulate`) — removed only the self-ref, kept the legitimate related word (e.g. order→delivery). Bank self-references now **0**.
- **Automatic re-resolution:** `refresh_refs_for_new_key()` runs after each ingestion (bounded query, no full scan on requests) to fill previously-unresolved refs that now point to a newly added canonical word.
- **Graph service** `build_word_graph()`: bounded one-hop, resolved IDs + display headwords, no duplicate nodes, no self-node, deterministic order, graceful unresolved handling (`{headword, id:null}`). Powers `GET /api/words/{id}` (same response shape; `confusing_words` additive). No multi-hop.
- **Quality report** extended with relationship metrics: total (1582), by type (syn 689/ant 456/rel 437/conf 0), resolved refs (91), unresolved (1491 — targets outside the 231-word bank; resolve as vocabulary grows), self-refs 0, duplicates 0, malformed 0, words-with-no-relationships, oversized sets.
- **Known unresolved behavior:** unresolved refs are expected and non-fatal — the word bank is small, so most relation targets aren't canonical words yet; they display by headword and auto-link later via targeted refresh. No UI change required.
- Tests: `backend/tests/test_graph_relationships.py` (resolution, integrity, migration idempotency/preservation, targeted refresh, graph builder, API regression). Phase A+B+C+core: **70 passed, 1 skipped**. Feature suites: 25 passed, 1 skipped, 2 pre-existing failures (TTS relative-URL test bug; stateful `lookup_ai_fallback`) — unchanged.

## Phase D — Adaptive Learning Engine (2026-09-30)
- **Pure engine** `backend/adaptive_learning.py` (deterministic, DB-free, no AI/randomness; every decision carries explainable `reason_codes`). Integrated into `practice/answer`, mission due-ranking, and Smart Review Nudges. MongoDB queries stay in `server.py`.
- **Signals used:** accuracy (lifetime + rolling `recent_results` window of 10), consistency (consecutive_correct), response time (normalized vs the learner's own average with sparse-history damping; omitted when absent), exposure (times_seen), current status, review timing (overdue/due/upcoming), and vocabulary metadata (CEFR/frequency/exam relevance — never equated directly to learner difficulty).
- **Mastery (0–100):** correct → `+12·diminish·speed_w (+3 if prev interval ≥7d)`, `diminish=1−0.75·mastery/100` (diminishing gains); wrong → `−(12+0.13·mastery)` (max −25). One miss never destroys, one hit never masters. First correct ≈ 11.
- **Confidence (0–100):** correct → `8 + min(consec,5)·1.2 + (speed−0.6)·8`, diminishing near top; wrong → `−18` (`−28` if the word was MASTERED). Tracks reliability separately from mastery.
- **Difficulty (0–1):** <2 exposures → deterministic CEFR prior (0.2–0.8); else blend of error-rate/low-mastery/low-confidence/slowness with a light prior. Personal, not CEFR.
- **Interval (days, bounds 1–180):** fail → relearn in 10 min (interval 0); success → base growth by consecutive `[1,1,2,4,8,16,32,60,100,180]` × strength(mastery+confidence 0.6–1.5) × (1.2−0.5·difficulty), capped at 2 days when confidence <40.
- **Status thresholds:** MASTERED = mastery≥85 ∧ confidence≥80 ∧ consecutive≥4; RECALLING = mastery≥55; LEARNING = mastery≥25; SEEN = attempted; NEW = never. Reaching MASTERED needs ~10–11 sustained correct recalls; a mastered failure demotes to RECALLING (moderate) or LEARNING (severe), never resets.
- **Priority (0–1):** `0.32·overdue + 0.24·weakness + 0.16·low_conf + 0.12·recent_error + 0.10·status_weight + 0.06·exam_boost` — exam relevance is capped so it never overrides evidence. Returns reason codes.
- **Slipping (0–1):** `0.4·failed_after_long_interval + 0.25·(low_conf∧mid_mastery) + 0.2·recent_error_rate + 0.15·overdue`. Used only for ranking nudges (candidate set still the due-within-2-days, mastery<90 words, preserving existing behavior). Does not notify.
- **Fields added (additive, lazy defaults):** `difficulty`, `confidence_score` (already existed), `recent_results` (capped 10), `last_reason_codes`. No migration of existing progress; missing fields default safely. `practice/answer` response gains additive `confidence_score`, `difficulty`, `reason_codes`.
- **Timezone:** all datetimes coerced to aware UTC; no naive arithmetic. User-local timezones out of scope (documented limitation) — UTC used consistently.
- Tests: `backend/tests/test_adaptive_learning.py` (20 deterministic behaviors + API regression). Phase A+B+C+D+core: **86 passed, 1 skipped**. Feature suites: 25 passed, 1 skipped, 2 pre-existing failures (TTS relative-URL test bug; stateful `lookup_ai_fallback`) — unchanged.

## Backlog (prioritized)
- **P0 (next, Phase E):** practice-mode architecture — clean question-mode registry so new modes (antonym, type-definition, sentence completion, context, audio recognition, usage, short written) can be added without rewriting the engine; adaptive engine chooses the mode.
- **P1:** exam/PYQ/curriculum architecture (F–H); AI provider abstraction (K).
- **P2:** production security (P), admin/content (O), offline (M), web (Q), Supabase/Postgres decision (R), real IAP/RevenueCat (S).

## Next Tasks
1. Phase E — practice-mode architecture.
2. Phase F — exam platform expansion.
3. Phase K — AI provider abstraction.

