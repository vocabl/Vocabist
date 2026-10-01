"""Vocabist backend API test suite - covers all endpoints listed in review request."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://learn-preview-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def fresh_user():
    """Register a fresh user for a full onboarding + practice run."""
    email = f"test_{uuid.uuid4().hex[:10]}@vocabist.app"
    password = "TestPass123"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": password, "name": "TEST User"
    }, timeout=30)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["email"] == email
    assert data["user"]["onboarded"] is False
    return {"email": email, "password": password, "token": data["token"], "user": data["user"]}


@pytest.fixture(scope="session")
def headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def demo_headers():
    """Demo (already onboarded) user for progress/exam-active tests."""
    r = requests.post(f"{API}/auth/login", json={
        "email": "demo@vocably.app", "password": "demo1234"
    }, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"demo login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


# ---------------- health / root ----------------
def test_health():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("service") == "vocabist"


# ---------------- auth ----------------
def test_register_duplicate_rejected(fresh_user):
    r = requests.post(f"{API}/auth/register", json={
        "email": fresh_user["email"], "password": "x123456", "name": "dup"
    }, timeout=15)
    assert r.status_code == 409


def test_login_success_and_bad_password(fresh_user):
    good = requests.post(f"{API}/auth/login", json={
        "email": fresh_user["email"], "password": fresh_user["password"]
    }, timeout=15)
    assert good.status_code == 200 and "token" in good.json()
    bad = requests.post(f"{API}/auth/login", json={
        "email": fresh_user["email"], "password": "wrongwrong"
    }, timeout=15)
    assert bad.status_code == 401


def test_me_endpoint(headers, fresh_user):
    r = requests.get(f"{API}/auth/me", headers=headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == fresh_user["email"]


def test_me_requires_auth():
    r = requests.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 401


# ---------------- onboarding ----------------
def test_onboarding_sets_onboarded(headers):
    body = {
        "reason": "exam_prep", "level": "B2", "daily_minutes": 15,
        "exam_slug": "ielts", "exam_date": "2026-06-01", "target_score": 7.0
    }
    r = requests.post(f"{API}/onboarding", json=body, headers=headers, timeout=15)
    assert r.status_code == 200
    prof = r.json()["profile"]
    assert prof["reason"] == "exam_prep"
    assert prof["level"] == "B2"
    assert prof["exam_slug"] == "ielts"
    # verify onboarded flag flipped
    me = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()
    assert me["user"]["onboarded"] is True


# ---------------- mission ----------------
def test_mission_shape(headers):
    r = requests.get(f"{API}/mission", headers=headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("total_words", "review_count", "new_count", "estimated_minutes", "streak", "xp"):
        assert k in d, f"missing {k}"
    assert isinstance(d["total_words"], int)


# ---------------- words ----------------
def test_words_list_and_filters(headers):
    r = requests.get(f"{API}/words", headers=headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 15
    assert len(body["words"]) > 0
    for w in body["words"]:
        assert "id" in w and "headword" in w and "saved" in w and "status" in w

    r2 = requests.get(f"{API}/words", headers=headers, params={"cefr": "C1"}, timeout=15)
    assert r2.status_code == 200
    assert all(w["cefr"] == "C1" for w in r2.json()["words"])

    r3 = requests.get(f"{API}/words", headers=headers, params={"search": "abate"}, timeout=15)
    assert r3.status_code == 200
    assert any(w["headword"] == "abate" for w in r3.json()["words"])

    r4 = requests.get(f"{API}/words", headers=headers, params={"exam": "ielts"}, timeout=15)
    assert r4.status_code == 200
    assert r4.json()["total"] >= 1


def test_word_detail_and_graph(headers):
    r = requests.get(f"{API}/words/abate", headers=headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["word"]["headword"] == "abate"
    assert "graph" in d and "synonyms" in d["graph"]
    # diminish IS in seed - should resolve to a real id
    assert isinstance(d["graph"]["synonyms"], list) and len(d["graph"]["synonyms"]) >= 1
    for s in d["graph"]["synonyms"]:
        assert "headword" in s
    assert isinstance(d["exams"], list)


def test_word_detail_404(headers):
    r = requests.get(f"{API}/words/nonexistent-xyz", headers=headers, timeout=15)
    assert r.status_code == 404


def test_save_unsave_flow(headers):
    s = requests.post(f"{API}/words/abate/save", headers=headers, timeout=15)
    assert s.status_code == 200 and s.json()["saved"] is True
    saved = requests.get(f"{API}/saved", headers=headers, timeout=15)
    assert saved.status_code == 200
    assert any(w["id"] == "abate" for w in saved.json()["words"])
    u = requests.delete(f"{API}/words/abate/save", headers=headers, timeout=15)
    assert u.status_code == 200 and u.json()["saved"] is False


# ---------------- topics / exams ----------------
def test_topics(headers):
    r = requests.get(f"{API}/topics", headers=headers, timeout=15)
    assert r.status_code == 200
    topics = r.json()["topics"]
    assert len(topics) >= 6
    assert all("word_count" in t for t in topics)


def test_exams(headers):
    r = requests.get(f"{API}/exams", headers=headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert len(d["exams"]) >= 6
    assert d["active_exam"] == "ielts"  # from onboarding
    assert any(e["active"] for e in d["exams"])


def test_exam_detail(headers):
    r = requests.get(f"{API}/exams/ielts", headers=headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["exam"]["slug"] == "ielts"
    assert isinstance(d["total_words"], int) and d["total_words"] >= 1
    assert d["is_active"] is True
    assert d["days_left"] is not None


def test_exam_detail_404(headers):
    r = requests.get(f"{API}/exams/nope-xxx", headers=headers, timeout=15)
    assert r.status_code == 404


def test_set_exam_goal(headers):
    r = requests.post(f"{API}/profile/exam-goal", json={
        "exam_slug": "toefl", "exam_date": "2026-08-01", "target_score": 100
    }, headers=headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["profile"]["exam_slug"] == "toefl"
    # revert to ielts for downstream tests
    requests.post(f"{API}/profile/exam-goal", json={
        "exam_slug": "ielts", "exam_date": "2026-06-01", "target_score": 7.0
    }, headers=headers, timeout=15)


# ---------------- practice ----------------
def test_practice_start_mission(headers):
    r = requests.post(f"{API}/practice/start?source=mission", headers=headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d["count"] > 0
    q = d["questions"][0]
    for k in ("word_id", "mode", "prompt", "answer", "card"):
        assert k in q, f"missing {k}"
    assert q["card"]["headword"]


def test_practice_start_variants(headers):
    for src, ref in [("topic", "academic"), ("exam", "ielts"), ("word", "abate"), ("saved", None)]:
        url = f"{API}/practice/start?source={src}" + (f"&ref={ref}" if ref else "")
        r = requests.post(url, headers=headers, timeout=20)
        assert r.status_code == 200, f"{src} failed {r.status_code} {r.text}"
        d = r.json()
        assert "questions" in d


def test_practice_answer_and_complete(headers):
    start = requests.post(f"{API}/practice/start?source=word&ref=ubiquitous", headers=headers, timeout=20).json()
    assert start["count"] >= 1
    q = start["questions"][0]
    ans = requests.post(f"{API}/practice/answer", json={
        "word_id": q["word_id"], "mode": q["mode"], "correct": True, "response_time_ms": 3000
    }, headers=headers, timeout=15)
    assert ans.status_code == 200
    d = ans.json()
    assert d["xp_gain"] == 10
    assert d["status"] in ("SEEN", "LEARNING", "RECALLING", "MASTERED")
    assert "next_review_at" in d

    wrong = requests.post(f"{API}/practice/answer", json={
        "word_id": q["word_id"], "mode": q["mode"], "correct": False, "response_time_ms": 5000
    }, headers=headers, timeout=15)
    assert wrong.status_code == 200 and wrong.json()["xp_gain"] == 2

    comp = requests.post(f"{API}/practice/complete", json={
        "answered": 2, "correct": 1, "duration_ms": 60000, "source": "word"
    }, headers=headers, timeout=15)
    assert comp.status_code == 200
    assert comp.json()["streak"] >= 1


# ---------------- progress ----------------
def test_progress_after_practice(headers):
    r = requests.get(f"{API}/progress", headers=headers, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("words_learned", "words_mastered", "accuracy", "streak", "xp", "level",
              "achievements", "weak_areas"):
        assert k in d
    assert d["xp"] >= 12  # 10 + 2 from prior test
    assert d["streak"] >= 1
    assert isinstance(d["achievements"], list) and len(d["achievements"]) >= 6


# ---------------- logout ----------------
def test_logout_invalidates(fresh_user):
    # Login fresh so we don't kill the session fixture used by earlier tests
    login = requests.post(f"{API}/auth/login", json={
        "email": fresh_user["email"], "password": fresh_user["password"]
    }, timeout=15).json()
    h = {"Authorization": f"Bearer {login['token']}"}
    lo = requests.post(f"{API}/auth/logout", headers=h, timeout=15)
    assert lo.status_code == 200
    me = requests.get(f"{API}/auth/me", headers=h, timeout=15)
    assert me.status_code == 401


# ---------------- demo user progress ----------------
def test_demo_user_progress(demo_headers):
    r = requests.get(f"{API}/progress", headers=demo_headers, timeout=15)
    assert r.status_code == 200
