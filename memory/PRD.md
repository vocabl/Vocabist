# Vocably — Product Requirements Document

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

## Backlog (prioritized)
- **P0:** Expand canonical word bank (seed synonyms as real headwords so graph chips are all tappable); more words per exam/topic.
- **P1:** AI features (explanations, mnemonics, example generation, quiz gen, reading passages) via Emergent key; Read & Learn; Learn From Anything (PDF/image/text extraction).
- **P1:** Audio pronunciation (US/UK) + audio caching.
- **P2:** Full entitlement/paywall + IAP (RevenueCat), offline packs/sync, admin content system, PYQ system, school/curriculum system, leaderboards, SEO web.

## Next Tasks
1. Grow vocabulary content and cross-link the knowledge graph.
2. Add AI-powered word explanations and example generation.
3. Add pronunciation audio.
4. Build the paywall + Pro entitlement gating.
