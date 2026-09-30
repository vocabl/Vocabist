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

## Backlog (prioritized)
- **P0 (next, Phase B):** content ingestion/validation pipeline + provenance (CURATED/AI_GENERATED/IMPORTED/ADMIN_CREATED) + content lifecycle (DRAFT/REVIEW/PUBLISHED/ARCHIVED); validation for duplicates/invalid relations/missing definitions/CEFR/exam refs before scaling the word bank.
- **P1 (Phase C+):** strengthen knowledge graph (backfill relation refs when new targets are added; resolve confusing-word/word-family targets); adaptive engine signals; practice-mode architecture; exam/PYQ/curriculum architecture; AI provider abstraction.
- **P2:** production security, admin/content system, offline foundation, web platform, Supabase/Postgres migration decision, real IAP/RevenueCat.

## Next Tasks
1. Phase B — content ingestion/validation architecture + provenance/lifecycle (do NOT mass-generate words yet).
2. Phase C — knowledge-graph strengthening (canonical ref backfill for new words).
3. Phase D — adaptive learning engine signals.

