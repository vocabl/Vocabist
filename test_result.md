backend:
  - task: "Authentication Flow (Login)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ Login endpoint working correctly. Successfully authenticated with demo@vocably.app credentials. Token received and validated."

  - task: "Authentication Flow (Session Validation)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/auth/me working correctly with Bearer token. Session validation successful."

  - task: "Vocabulary Operations (List Words)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/words?limit=5 working correctly. Returns 231 total words as expected. Data retrieved from Supabase."

  - task: "Vocabulary Operations (Word Detail)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/words/abate working correctly. Returns word detail with graph structure. Minor: Graph has 0 nodes (may need relationship data)."

  - task: "Vocabulary Operations (Topics)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/topics working correctly. Returns 6 topics."

  - task: "Vocabulary Operations (Exams)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/exams working correctly. Returns 6 exams."

  - task: "Practice Flow (Start Practice)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ POST /api/practice/start?source=mission working correctly. Returns 12 questions for practice."

  - task: "Practice Flow (Submit Answer)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ POST /api/practice/answer working correctly. XP updated successfully (gained 10 XP). Word status updated to SEEN."

  - task: "Progress/Mission (Mission Data)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/mission working correctly. Returns mission data with 12 total words (0 review, 12 new)."

  - task: "Progress/Mission (User Progress)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/progress working correctly. Returns user progress with XP: 20, Level: 1, Words learned: 0."

  - task: "Entitlements"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ GET /api/entitlements working correctly. Returns tier: pro with unlimited limits."

  - task: "Data Integrity (Supabase Backend)"
    implemented: true
    working: true
    file: "backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ Backend configured with DB_BACKEND=supabase. Data is being retrieved from Supabase, not MongoDB."

  - task: "RLS (Row Level Security)"
    implemented: true
    working: true
    file: "backend/db/supabase_repo.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ RLS is not blocking service-role access. All API endpoints working correctly with Supabase service role key."

  # ---------------- NVIDIA AI Platform + Admin Control Center (P1) ----------------
  - task: "AI Gateway + NVIDIA provider (7 models) + routing + fallback"
    implemented: true
    working: true
    file: "backend/ai/*"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Central AI Gateway with NVIDIA provider (chat/embeddings), Emergent fallback. 7 NVIDIA models + emergent registered. Capability-validated task routing + intelligent fallback. Verified live: nemotron-lightning ping AVAILABLE, embeddings 2048-dim, fallback chain exercised. 11 unit tests pass (tests/test_ai_platform.py)."

  - task: "Admin API (server-side protected) — dashboard/models/routing/jobs/usage/review"
    implemented: true
    working: true
    file: "backend/admin_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "All /api/admin/* require admin email allowlist (ADMIN_EMAILS). Verified: dashboard real counts, model toggle/ping, routing view, generation job create+poll (dedupes vs 766 words), review queue, publish/approve/reject/archive, translate/embed. Non-admin users get 403."

  - task: "Async generation jobs → content pipeline → REVIEW (no auto-publish)"
    implemented: true
    working: true
    file: "backend/ai/jobs.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Jobs run as asyncio background tasks, persisted to file store. Generated words go through content_ingest.bulk_ingest (provenance=AI_GENERATED) → status REVIEW. Verified a new AI word lands in REVIEW and can be published via admin."

  - task: "AI Coach routed through gateway (behavior + entitlements preserved)"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "POST /api/words/{id}/ai-coach now routes via gateway AI_COACH task (Emergent GPT-5.6 Luna primary). Output contract {explanation,example,mnemonic} + free daily quota unchanged."

frontend:
  - task: "Admin Control Center UI (admin-only, inside Expo app)"
    implemented: true
    working: true
    file: "frontend/app/admin/*"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Admin entry in Progress/Profile tab (visible only if /admin/me is_admin). Screens: dashboard, models (toggle+ping), routing, jobs (create+monitor), usage, review (publish/reject/regenerate field). Verified dashboard renders real data + honest provider health."

  - task: "Frontend Testing"
    implemented: false
    working: "NA"
    file: ""
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "testing"
        comment: "Frontend testing not performed as per instructions (backend testing only)."

metadata:
  created_by: "testing_agent"
  version: "1.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "AI Gateway + NVIDIA provider (7 models) + routing + fallback"
    - "Admin API (server-side protected) — dashboard/models/routing/jobs/usage/review"
    - "Async generation jobs → content pipeline → REVIEW (no auto-publish)"
    - "AI Coach routed through gateway (behavior + entitlements preserved)"
    - "Admin Control Center UI (admin-only, inside Expo app)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: "✅ ALL BACKEND TESTS PASSED (13/13). Vocabist backend is working correctly with Supabase database and RLS enabled. All critical endpoints verified: authentication, vocabulary operations, practice flow, progress/mission, and entitlements. Data is being retrieved from Supabase (not MongoDB). RLS is not blocking service-role access. No regression detected after RLS enablement. Previous acceptance: 50/50 PASS maintained."
  - agent: "main"
    message: "Implemented NVIDIA AI Platform + Admin Control Center P1 (additive). New backend/ai/* gateway, backend/admin_routes.py, frontend/app/admin/*. Admin auth = ADMIN_EMAILS allowlist on existing custom auth."
  - agent: "main"
    message: "FIXED critical bug from iteration_6: AI-generated words with a free-text topic violated words.topic→topics.slug FK. content_ingest now coerces any unknown topic to NULL (all ingest paths). Verified: generation job COMPLETED with 3 new words (syzygy/numinous/apocrypha) in REVIEW (topic NULL); regenerate synonyms, reject→ARCHIVED, publish→PUBLISHED, archive all return 200. Temporary qa_admin removed from ADMIN_EMAILS; only imsunil0202@gmail.com remains admin."
