"""Vocably iteration 2 - tests for new features:
- Entitlements
- Subscription activate/cancel
- AI Coach (gpt-5.6-luna via emergent)
- Pronounce It audio (Dictionary API + TTS fallback + /api/tts/{key}.mp3)
- Word bank scale (~230 words, exam filter, GRE locked for free)
- Quick regression: mission cap, practice flows, words list still work
"""
import os
import uuid
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env value
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
                break
API = f"{BASE_URL}/api"


def _register_onboard():
    email = f"test_{uuid.uuid4().hex[:10]}@vocably.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123", "name": "TEST User"
    }, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    # onboard so mission works
    requests.post(f"{API}/onboarding", json={
        "reason": "exam_prep", "level": "B2", "daily_minutes": 15,
        "exam_slug": "ielts", "exam_date": "2026-06-01", "target_score": 7.0
    }, headers=h, timeout=30)
    return email, h


@pytest.fixture(scope="module")
def user_a():
    email, h = _register_onboard()
    return {"email": email, "headers": h}


@pytest.fixture(scope="module")
def user_fresh():
    """Fresh user for locked-exam / paywall tests."""
    email, h = _register_onboard()
    return {"email": email, "headers": h}


# ---------- entitlements ----------
def test_entitlements_free_shape(user_a):
    r = requests.get(f"{API}/entitlements", headers=user_a["headers"], timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tier"] == "free"
    assert d["is_pro"] is False
    assert d["limits"]["daily_new_words"] == 8
    assert d["limits"]["ai_coach_per_day"] == 3
    assert "gre" in d["limits"]["locked_exams"]
    assert "gmat" in d["limits"]["locked_exams"]
    assert isinstance(d["ai_coach_used_today"], int)


def test_subscription_activate_and_cancel(user_a):
    h = user_a["headers"]
    r = requests.post(f"{API}/subscription/activate", json={"plan": "monthly"},
                      headers=h, timeout=15)
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"

    e = requests.get(f"{API}/entitlements", headers=h, timeout=15).json()
    assert e["tier"] == "pro"
    assert e["is_pro"] is True
    assert e["limits"]["locked_exams"] == []
    assert e["limits"]["daily_new_words"] >= 9999

    c = requests.post(f"{API}/subscription/cancel", headers=h, timeout=15)
    assert c.status_code == 200
    assert c.json()["tier"] == "free"

    e2 = requests.get(f"{API}/entitlements", headers=h, timeout=15).json()
    assert e2["tier"] == "free"
    assert e2["is_pro"] is False


# ---------- word bank scale ----------
def test_word_bank_scale(user_a):
    h = user_a["headers"]
    r = requests.get(f"{API}/words", params={"limit": 1}, headers=h, timeout=15)
    assert r.status_code == 200
    total = r.json()["total"]
    assert total >= 200, f"word bank total={total}, expected ~230"

    # cefr filter (all six)
    for lvl in ("A1", "A2", "B1", "B2", "C1", "C2"):
        rr = requests.get(f"{API}/words", params={"cefr": lvl, "limit": 5},
                          headers=h, timeout=15)
        assert rr.status_code == 200, f"cefr {lvl}: {rr.text}"
        for w in rr.json()["words"]:
            assert w["cefr"] == lvl

    # gre has many words
    g = requests.get(f"{API}/words", params={"exam": "gre", "limit": 1},
                     headers=h, timeout=15)
    assert g.status_code == 200
    assert g.json()["total"] >= 20, f"gre words={g.json()['total']}"


# ---------- locked exam (free user) ----------
def test_gre_locked_for_free(user_fresh):
    h = user_fresh["headers"]
    r = requests.get(f"{API}/exams/gre", headers=h, timeout=15)
    assert r.status_code == 200
    assert r.json()["locked"] is True

    p = requests.post(f"{API}/practice/start", params={"source": "exam", "ref": "gre"},
                      headers=h, timeout=15)
    assert p.status_code == 402, f"expected 402 got {p.status_code} {p.text}"


def test_gre_unlocked_after_pro(user_fresh):
    h = user_fresh["headers"]
    requests.post(f"{API}/subscription/activate", json={"plan": "monthly"},
                  headers=h, timeout=15)
    r = requests.get(f"{API}/exams/gre", headers=h, timeout=15)
    assert r.json()["locked"] is False
    p = requests.post(f"{API}/practice/start", params={"source": "exam", "ref": "gre"},
                     headers=h, timeout=30)
    assert p.status_code == 200
    assert p.json()["count"] > 0
    # revert
    requests.post(f"{API}/subscription/cancel", headers=h, timeout=15)


# ---------- audio ----------
def test_audio_common_word(user_a):
    """Common word (e.g. abate) - expect dictionary or tts fallback URLs."""
    h = user_a["headers"]
    r = requests.get(f"{API}/words/abate/audio", headers=h, timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "us_url" in d and "uk_url" in d and "tts_url" in d
    # at least one of them should be present
    assert d["us_url"] or d["uk_url"] or d["tts_url"], f"no audio: {d}"


def test_tts_endpoint_serves_mp3(user_a):
    """Trigger TTS by asking audio for an obscure word (or reuse existing tts_url), then GET the mp3."""
    h = user_a["headers"]
    # pick an obscure headword from the bank - iterate words page and choose one without common dict entry
    words = requests.get(f"{API}/words", params={"limit": 50}, headers=h, timeout=15).json()["words"]
    tts_url = None
    for w in words:
        a = requests.get(f"{API}/words/{w['id']}/audio", headers=h, timeout=45)
        if a.status_code == 200 and a.json().get("tts_url"):
            tts_url = a.json()["tts_url"]
            break
    if not tts_url:
        pytest.skip("No word triggered TTS fallback in sample of 50 words")

    # /api/tts/{key}.mp3 - use requests without auth (endpoint is public)
    mp3 = requests.get(tts_url, timeout=30)
    assert mp3.status_code == 200, f"tts fetch failed: {mp3.status_code}"
    assert mp3.headers.get("content-type", "").startswith("audio/mpeg")
    assert len(mp3.content) > 500  # non-trivial mp3 payload


# ---------- AI coach ----------
def test_ai_coach_generates_and_caches(user_a):
    """Generate for one word, verify cache returns same content and doesn't count against limit."""
    h = user_a["headers"]
    # find a word that likely hasn't been coached yet - use a random unique headword
    words = requests.get(f"{API}/words", params={"limit": 100}, headers=h, timeout=15).json()["words"]
    assert words, "no words returned"
    # pick a mid-list one
    target = words[len(words) // 2]["id"]

    r = requests.post(f"{API}/words/{target}/ai-coach", headers=h, timeout=90)
    assert r.status_code == 200, f"ai-coach failed: {r.status_code} {r.text}"
    d = r.json()
    assert "content" in d
    c = d["content"]
    for k in ("explanation", "example", "mnemonic"):
        assert k in c and isinstance(c[k], str) and c[k].strip(), f"missing {k}"

    # request again - should be cached
    r2 = requests.post(f"{API}/words/{target}/ai-coach", headers=h, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    assert r2.json()["content"] == c


def test_ai_coach_free_limit(user_fresh):
    """On a fresh free user: cached-word coach doesn't count against limit;
       4 DISTINCT never-coached words should hit 402 on the 4th."""
    h = user_fresh["headers"]
    # ensure back to free
    requests.post(f"{API}/subscription/cancel", headers=h, timeout=15)

    # collect a bunch of candidate words - pick ones with no cache yet by trying them
    words = requests.get(f"{API}/words", params={"limit": 100}, headers=h, timeout=15).json()["words"]
    # add more by paginating
    more = requests.get(f"{API}/words", params={"limit": 100, "offset": 100}, headers=h, timeout=15).json().get("words", [])
    words = words + more
    uncoached = []
    # heuristic: use words from higher-indexed part of list to avoid ones cached by earlier tests
    # start from the end and try until we find 4 non-cached ones
    for w in reversed(words):
        r = requests.post(f"{API}/words/{w['id']}/ai-coach", headers=h, timeout=90)
        if r.status_code == 200 and r.json().get("cached") is True:
            continue  # cached from earlier; doesn't count
        if r.status_code == 200 and r.json().get("cached") is False:
            uncoached.append(w["id"])
            if len(uncoached) >= 3:
                break
        elif r.status_code == 402:
            # already hit limit somehow
            uncoached.append("LIMIT")
            break
        else:
            # e.g. 502 AI busy - skip
            continue

    # now attempt a 4th unique never-coached word and expect 402
    hit_402 = False
    for w in words:
        if w["id"] in uncoached:
            continue
        r = requests.post(f"{API}/words/{w['id']}/ai-coach", headers=h, timeout=90)
        if r.status_code == 402:
            hit_402 = True
            break
        if r.status_code == 200 and r.json().get("cached") is True:
            # cached word doesn't count - keep trying
            continue
        if r.status_code == 200 and r.json().get("cached") is False:
            # still under limit? means we found another uncached word before hitting 3
            uncoached.append(w["id"])
            if len(uncoached) >= 4:
                # unexpected: 4 succeeded without 402
                break
        else:
            continue
    assert hit_402, f"expected 402 after 3 unique AI-coach generations; uncoached={uncoached}"


# ---------- regression: mission free-tier new-word cap ----------
def test_mission_free_new_cap(user_a):
    h = user_a["headers"]
    # ensure user_a is free
    requests.post(f"{API}/subscription/cancel", headers=h, timeout=15)
    r = requests.get(f"{API}/mission", headers=h, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["new_count"] <= 8, f"free tier new_count={d['new_count']} > 8"


# ---------- regression: quick auth+practice sanity ----------
def test_practice_start_answer_complete_regression(user_a):
    h = user_a["headers"]
    s = requests.post(f"{API}/practice/start", params={"source": "word", "ref": "abate"},
                      headers=h, timeout=20).json()
    assert s["count"] >= 1
    q = s["questions"][0]
    a = requests.post(f"{API}/practice/answer", json={
        "word_id": q["word_id"], "mode": q["mode"], "correct": True, "response_time_ms": 3000
    }, headers=h, timeout=15)
    assert a.status_code == 200
    assert a.json()["xp_gain"] == 10
    c = requests.post(f"{API}/practice/complete", json={
        "answered": 1, "correct": 1, "duration_ms": 30000, "source": "word"
    }, headers=h, timeout=15)
    assert c.status_code == 200
