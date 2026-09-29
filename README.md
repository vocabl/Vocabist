# Vocably

A mobile-first English vocabulary learning platform (Expo + FastAPI + MongoDB).

Core learning loop: **Discover → Understand → Recall → Use → Review → Master**.

## Stack
- **Mobile:** Expo (React Native) + TypeScript, expo-router, @tanstack/react-query
- **Backend:** FastAPI + MongoDB (Motor)
- **Auth:** Email/password (bcrypt) + Emergent-managed Google OAuth (Bearer session tokens)

## Environment variables
### frontend/.env
- `EXPO_PUBLIC_BACKEND_URL` — backend base URL (API routes are under `/api`)

### backend/.env
- `MONGO_URL` — MongoDB connection string
- `DB_NAME` — database name
- `CORS_ORIGINS` — allowed origins (`*` for mobile)
- `JWT_SECRET` — server secret
- `EMERGENT_LLM_KEY` — universal AI key (used for Phase 5 AI features)

## Key API routes (all under `/api`)
- Auth: `POST /auth/register`, `POST /auth/login`, `POST /auth/session`, `GET /auth/me`, `POST /auth/logout`
- Profile: `GET /profile`, `POST /onboarding`, `POST /profile/exam-goal`
- Vocabulary: `GET /words`, `GET /words/{id}`, `POST|DELETE /words/{id}/save`, `GET /saved`, `GET /topics`
- Exams: `GET /exams`, `GET /exams/{slug}`
- Learning: `GET /mission`, `POST /practice/start`, `POST /practice/answer`, `POST /practice/complete`
- Progress: `GET /progress`, `POST /analytics`

## Run
Services are managed by supervisor (`expo`, `backend`, `mongodb`). The backend seeds
words/topics/exams on first startup.
