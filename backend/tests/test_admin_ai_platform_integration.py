"""End-to-end integration tests for the Vocabist Admin AI Platform (P1).

Covers:
- Admin authorization (admin vs student)
- GET /api/admin/dashboard
- GET /api/admin/ai/models + toggle + ping
- GET /api/admin/ai/routing + PUT (invalid chain rejection)
- POST /api/admin/ai/jobs (vocabulary generation) with job polling
- Review queue workflow (publish/reject/archive/regenerate)
- /api/admin/ai/translate and /api/admin/ai/embed
- Student regression (login/words/mission/practice/progress/entitlements/ai-coach)
"""
import os
import time
import pytest
import requests


BASE_URL = os.environ.get(
    "EXPO_BACKEND_URL",
    "https://526c603b-63ae-4637-8dc1-72f2fc007544.preview.emergentagent.com",
).rstrip("/")

ADMIN_EMAIL = "qa_admin@vocabist.com"
ADMIN_PASSWORD = "adminpass123"
STUDENT_EMAIL = "test@vocabist.com"
STUDENT_PASSWORD = "test1234"


# -------------------- fixtures --------------------

@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def student_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Student login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# -------------------- admin authorization --------------------

class TestAdminAuthorization:
    def test_student_cannot_access_dashboard(self, student_token):
        r = requests.get(f"{BASE_URL}/api/admin/dashboard", headers=auth(student_token), timeout=30)
        assert r.status_code == 403, f"Expected 403 for student, got {r.status_code}"

    def test_student_cannot_access_models(self, student_token):
        r = requests.get(f"{BASE_URL}/api/admin/ai/models", headers=auth(student_token), timeout=30)
        assert r.status_code == 403

    def test_student_cannot_access_routing(self, student_token):
        r = requests.get(f"{BASE_URL}/api/admin/ai/routing", headers=auth(student_token), timeout=30)
        assert r.status_code == 403

    def test_student_cannot_create_job(self, student_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/ai/jobs",
            headers=auth(student_token),
            json={"count": 2, "cefr": "C1", "topic": "Science"},
            timeout=30,
        )
        assert r.status_code == 403

    def test_student_cannot_access_review(self, student_token):
        r = requests.get(f"{BASE_URL}/api/admin/vocabulary/review", headers=auth(student_token), timeout=30)
        assert r.status_code == 403

    def test_admin_me_for_student(self, student_token):
        r = requests.get(f"{BASE_URL}/api/admin/me", headers=auth(student_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["is_admin"] is False
        assert data["email"] == STUDENT_EMAIL

    def test_admin_me_for_admin(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/me", headers=auth(admin_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["is_admin"] is True
        assert data["email"] == ADMIN_EMAIL

    def test_unauth_blocked(self):
        r = requests.get(f"{BASE_URL}/api/admin/dashboard", timeout=30)
        assert r.status_code in (401, 403)


# -------------------- dashboard --------------------

class TestDashboard:
    def test_dashboard_shape_and_real_counts(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/dashboard", headers=auth(admin_token), timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # Vocabulary
        v = d["vocabulary"]
        for k in ("total", "published", "review", "draft", "archived", "ai_generated"):
            assert k in v, f"missing vocab.{k}"
            assert isinstance(v[k], int)
        assert v["total"] >= 1, "DB should have words"
        # AI usage aggregate
        assert "ai" in d
        for k in ("requests_total", "success_rate", "fallback_rate", "by_model"):
            assert k in d["ai"]
        # Providers list with real statuses
        assert isinstance(d["providers"], list)
        assert len(d["providers"]) >= 8
        allowed_status = {"AVAILABLE", "UNAVAILABLE", "UNKNOWN", "DISABLED"}
        for m in d["providers"]:
            assert "status" in m
            assert m["status"] in allowed_status, f"invalid provider status {m['status']}"
            # no fake 'OK' or 'HEALTHY'
            assert m["status"] not in ("OK", "HEALTHY")
        # Jobs summary
        assert "jobs" in d
        for k in ("total", "running", "completed", "partial", "failed"):
            assert k in d["jobs"]


# -------------------- models --------------------

class TestModels:
    def test_models_list(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/ai/models", headers=auth(admin_token), timeout=30)
        assert r.status_code == 200
        models = r.json()["models"]
        keys = {m["key"] for m in models}
        expected = {
            "nemotron-lightning", "kimi-k3", "gpt-oss-20b", "nemotron-embed",
            "riva-translate", "nemotron-super", "muse-glimmer", "emergent-luna",
        }
        assert expected.issubset(keys), f"missing: {expected - keys}"
        for m in models:
            assert "capabilities" in m and isinstance(m["capabilities"], list)
            assert "modality" in m or "provider" in m  # at least metadata present

    def test_toggle_model_round_trip(self, admin_token):
        key = "muse-glimmer"
        # read current
        r = requests.get(f"{BASE_URL}/api/admin/ai/models", headers=auth(admin_token), timeout=30)
        models = {m["key"]: m for m in r.json()["models"]}
        current = models[key].get("enabled", True)
        # flip
        r2 = requests.post(
            f"{BASE_URL}/api/admin/ai/models/{key}/toggle",
            headers=auth(admin_token),
            json={"enabled": not current},
            timeout=30,
        )
        assert r2.status_code == 200
        assert r2.json()["enabled"] == (not current)
        # flip back
        r3 = requests.post(
            f"{BASE_URL}/api/admin/ai/models/{key}/toggle",
            headers=auth(admin_token),
            json={"enabled": current},
            timeout=30,
        )
        assert r3.status_code == 200
        assert r3.json()["enabled"] == current

    def test_ping_nemotron_lightning_real_status(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/ai/models/nemotron-lightning/ping",
            headers=auth(admin_token),
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "status" in data
        assert data["status"] in ("AVAILABLE", "UNAVAILABLE"), f"ping returned non-real status {data['status']}"


# -------------------- routing --------------------

class TestRouting:
    def test_routing_list_shape(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/ai/routing", headers=auth(admin_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "routing" in data and "tasks" in data
        # 12 tasks expected (per request)
        assert len(data["routing"]) == 12, f"expected 12 tasks, got {len(data['routing'])}"
        for row in data["routing"]:
            assert "task" in row
            assert "chain" in row
            assert "required_capability" in row
            assert isinstance(row["chain"], list)

    def test_routing_rejects_incapable_chain_embed_for_generation(self, admin_token):
        r = requests.put(
            f"{BASE_URL}/api/admin/ai/routing",
            headers=auth(admin_token),
            json={"task": "vocabulary_generation", "chain": ["nemotron-embed"], "enabled": True},
            timeout=30,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"

    def test_routing_rejects_translate_for_classification(self, admin_token):
        r = requests.put(
            f"{BASE_URL}/api/admin/ai/routing",
            headers=auth(admin_token),
            json={"task": "classification", "chain": ["riva-translate"], "enabled": True},
            timeout=30,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


# -------------------- generation jobs --------------------

GENERATED_JOB_ID = {"id": None}


class TestGenerationJobs:
    def test_create_job_and_poll(self, admin_token):
        payload = {"count": 3, "cefr": "C1", "topic": "Rare Academic"}
        r = requests.post(
            f"{BASE_URL}/api/admin/ai/jobs",
            headers=auth(admin_token),
            json=payload,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        job = r.json()
        assert "id" in job or "job_id" in job
        job_id = job.get("id") or job.get("job_id")
        GENERATED_JOB_ID["id"] = job_id
        assert job.get("status") in ("QUEUED", "RUNNING", "PENDING"), job

        # Poll up to 90s
        deadline = time.time() + 100
        final = None
        last_status = None
        while time.time() < deadline:
            rp = requests.get(f"{BASE_URL}/api/admin/ai/jobs/{job_id}", headers=auth(admin_token), timeout=30)
            assert rp.status_code == 200
            data = rp.json()
            last_status = data.get("status")
            if last_status in ("COMPLETED", "PARTIAL", "FAILED"):
                final = data
                break
            time.sleep(3)
        assert final is not None, f"job did not finish within 100s, last status={last_status}"
        assert final["status"] in ("COMPLETED", "PARTIAL"), f"job did not succeed: {final}"

    def test_new_words_are_review_not_published(self, admin_token):
        # Confirm new generated words land in REVIEW
        r = requests.get(
            f"{BASE_URL}/api/admin/vocabulary/review?limit=50",
            headers=auth(admin_token),
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "words" in data
        # All returned words must be REVIEW status
        for w in data["words"]:
            assert w.get("status") == "REVIEW", f"non-REVIEW word in review queue: {w.get('status')}"


# -------------------- review workflow --------------------

REVIEW_IDS = {"publish": None, "reject": None, "archive": None, "regen": None}


class TestReviewWorkflow:
    def _pick_review_ids(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/vocabulary/review?limit=50",
            headers=auth(admin_token),
            timeout=30,
        )
        assert r.status_code == 200
        words = r.json().get("words", [])
        return words

    def test_list_review(self, admin_token):
        words = self._pick_review_ids(admin_token)
        if not words:
            pytest.skip("No REVIEW words available to test workflow")
        # Reserve up to 4 ids for subsequent tests
        ids = [w["id"] for w in words[:4]]
        for role, _id in zip(["publish", "reject", "archive", "regen"], ids):
            REVIEW_IDS[role] = _id

    def test_regenerate_field(self, admin_token):
        if not REVIEW_IDS["regen"]:
            pytest.skip("no review word reserved")
        r = requests.post(
            f"{BASE_URL}/api/admin/vocabulary/{REVIEW_IDS['regen']}/regenerate",
            headers=auth(admin_token),
            json={"field": "synonyms"},
            timeout=120,
        )
        # 502 is acceptable if AI gateway fails, else must be 200
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            d = r.json()
            assert d.get("field") == "synonyms"
            assert "value" in d
            assert "word" in d

    def test_publish_review_word(self, admin_token):
        if not REVIEW_IDS["publish"]:
            pytest.skip("no review word reserved")
        r = requests.post(
            f"{BASE_URL}/api/admin/vocabulary/{REVIEW_IDS['publish']}/publish",
            headers=auth(admin_token),
            timeout=60,
        )
        # publish is validation-gated — may 400 if the generated word fails validation
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            assert r.json().get("status") == "PUBLISHED"

    def test_reject_review_word(self, admin_token):
        if not REVIEW_IDS["reject"]:
            pytest.skip("no review word reserved")
        r = requests.post(
            f"{BASE_URL}/api/admin/vocabulary/{REVIEW_IDS['reject']}/reject",
            headers=auth(admin_token),
            json={"reason": "low quality"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ARCHIVED"

    def test_archive_review_word(self, admin_token):
        if not REVIEW_IDS["archive"]:
            pytest.skip("no review word reserved")
        r = requests.post(
            f"{BASE_URL}/api/admin/vocabulary/{REVIEW_IDS['archive']}/archive",
            headers=auth(admin_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ARCHIVED"


# -------------------- AI services --------------------

class TestAIServices:
    def test_translate(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/ai/translate",
            headers=auth(admin_token),
            json={"text": "knowledge", "target_language": "Spanish"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # Response contract: should have translation (common keys)
        text_val = d.get("translation") or d.get("translated") or d.get("text") or ""
        assert text_val and isinstance(text_val, str), f"no translation value: {d}"

    def test_embed_query_returns_dimensions(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/ai/embed",
            headers=auth(admin_token),
            json={"text": "hello", "input_type": "query"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # The embedding payload shape: expect either 'embedding'/'vector'/'embeddings' list or dim count
        vec = d.get("embedding") or d.get("vector")
        if vec is None and "embeddings" in d and isinstance(d["embeddings"], list) and d["embeddings"]:
            vec = d["embeddings"][0]
        dims = d.get("dimensions") or d.get("dim") or (len(vec) if isinstance(vec, list) else 0)
        assert dims and dims > 0, f"embedding dims not > 0: {d}"


# -------------------- student regression --------------------

class TestStudentRegression:
    def test_login(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD},
            timeout=30,
        )
        assert r.status_code == 200
        assert "token" in r.json()

    def test_words(self, student_token):
        r = requests.get(f"{BASE_URL}/api/words?limit=5", headers=auth(student_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "words" in d or isinstance(d, list)

    def test_mission(self, student_token):
        r = requests.get(f"{BASE_URL}/api/mission", headers=auth(student_token), timeout=30)
        assert r.status_code == 200

    def test_practice_start(self, student_token):
        r = requests.post(
            f"{BASE_URL}/api/practice/start",
            headers=auth(student_token),
            json={"mode": "quick"},
            timeout=30,
        )
        # 200 or 400 (if mode mismatch) — but should not be 500/403
        assert r.status_code in (200, 400, 404), f"practice/start returned {r.status_code}: {r.text}"

    def test_progress(self, student_token):
        r = requests.get(f"{BASE_URL}/api/progress", headers=auth(student_token), timeout=30)
        assert r.status_code == 200

    def test_entitlements(self, student_token):
        r = requests.get(f"{BASE_URL}/api/entitlements", headers=auth(student_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "tier" in d or "entitlements" in d or "features" in d

    def test_ai_coach(self, student_token):
        # Pick a word to request coaching for
        rw = requests.get(f"{BASE_URL}/api/words?limit=1", headers=auth(student_token), timeout=30)
        assert rw.status_code == 200
        payload = rw.json()
        words = payload.get("words") if isinstance(payload, dict) else payload
        if not words:
            pytest.skip("No words available for ai-coach test")
        word_id = words[0].get("id") or words[0].get("word_id")
        r = requests.post(
            f"{BASE_URL}/api/words/{word_id}/ai-coach",
            headers=auth(student_token),
            timeout=90,
        )
        # 200 (normal) or 402/429 if quota depleted
        assert r.status_code in (200, 402, 429), f"ai-coach returned {r.status_code}: {r.text}"
        if r.status_code == 200:
            d = r.json()
            for k in ("explanation", "example", "mnemonic"):
                assert k in d, f"missing key {k} in ai-coach response"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
