# Vocably — Test Credentials

## Email/Password test account
- Email: `demo@vocably.app`
- Password: `demo1234`
- Name: Demo Student
- Notes: Created via /api/auth/register. Onboarded with IELTS goal (B2, 10 min/day).

## Google OAuth (Emergent-managed)
- Uses Emergent Google login flow (no app-managed password).
- Any Google account allowed; user is upserted by email.

## Backend
- Base URL (external): value of EXPO_PUBLIC_BACKEND_URL in /app/frontend/.env
- All API routes are prefixed with `/api`.
- Auth: send `Authorization: Bearer <token>` where token is returned by
  /api/auth/login, /api/auth/register, or /api/auth/session.
