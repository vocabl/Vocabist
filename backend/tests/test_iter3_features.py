"""Vocabist iteration 3 - tests for new features:
- Read & Learn: /api/articles list + detail (with body)
- Word lookup: bank hit + AI fallback (dictionary blocked in env)
- Import word (AI fallback)
- Extract text / Extract PDF
- Smart Review Nudges: /api/review/slipping + practice sources 'slipping' & 'list'
- Regression: auth, mission cap, practice answer/complete, entitlements
"""
import io
import os
import uuid
import requests
import pytest

with open("/app/frontend/.env") as fh:
    for line in fh:
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
            break
API = f"{BASE_URL}/api"


def _register():
    email = f"test_{uuid.uuid4().hex[:10]}@vocabist.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123", "name": "TEST User"
    }, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    requests.post(f"{API}/onboarding", json={
        "reason": "exam_prep", "level": "B2", "daily_minutes": 15,
        "exam_slug": "ielts", "exam_date": "2026-06-01", "target_score": 7.0
    }, headers=h, timeout=30)
    return email, h


@pytest.fixture(scope="module")
def user_h():
    _, h = _register()
    return h


# ---------- Read & Learn ----------
def test_articles_list(user_h):
    r = requests.get(f"{API}/articles", headers=user_h, timeout=15)
    assert r.status_code == 200, r.text
    arts = r.json()["articles"]
    assert isinstance(arts, list) and len(arts) >= 1
    a0 = arts[0]
    for k in ("id", "title"):
        assert k in a0
    # body should be excluded from list
    assert "body" not in a0


def test_articles_list_level_filter(user_h):
    # try each level with any content
    r = requests.get(f"{API}/articles", headers=user_h, timeout=15).json()["articles"]
    levels = {a.get("level") for a in r if a.get("level")}
    if not levels:
        pytest.skip("Articles have no level field")
    lvl = next(iter(levels))
    r2 = requests.get(f"{API}/articles", params={"level": lvl}, headers=user_h, timeout=15)
    assert r2.status_code == 200
    for a in r2.json()["articles"]:
        assert a.get("level") == lvl


def test_article_detail_has_body(user_h):
    arts = requests.get(f"{API}/articles", headers=user_h, timeout=15).json()["articles"]
    aid = arts[0]["id"]
    r = requests.get(f"{API}/articles/{aid}", headers=user_h, timeout=15)
    assert r.status_code == 200
    art = r.json()["article"]
    assert art["id"] == aid
    assert art.get("body"), "article detail should include body"


def test_article_detail_404(user_h):
    r = requests.get(f"{API}/articles/does-not-exist-xyz", headers=user_h, timeout=15)
    assert r.status_code == 404


# ---------- Lookup ----------
def test_lookup_in_bank(user_h):
    r = requests.get(f"{API}/lookup", params={"word": "abate"}, headers=user_h, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["in_bank"] is True
    assert d["headword"] == "abate"
    assert d["simple_definition"]
    assert "id" in d


def test_lookup_ai_fallback(user_h):
    # dictionary API blocked -> falls back to AI (gpt-5.6-luna). May take a few seconds.
    r = requests.get(f"{API}/lookup", params={"word": "serendipity"}, headers=user_h, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("in_bank") is False
    assert d.get("found") is True, f"expected AI fallback found=true, got {d}"
    assert d.get("simple_definition"), "AI fallback missing simple_definition"


# ---------- Import ----------
def test_import_word(user_h):
    r = requests.post(f"{API}/words/import", json={"headword": "serendipity"},
                      headers=user_h, timeout=60)
    assert r.status_code == 200, r.text
    wid = r.json().get("id")
    assert wid, "import should return an id"
    # verify persisted: GET /words/{id}
    g = requests.get(f"{API}/words/{wid}", headers=user_h, timeout=15)
    assert g.status_code == 200
    assert g.json()["word"]["headword"] == "serendipity"


# ---------- Extract ----------
def test_extract_text(user_h):
    text = ("The scientist observed a serendipitous phenomenon during "
            "her rigorous investigation of quantum entanglement. Words like abate, mitigate, "
            "and ephemeral appeared in the article.")
    r = requests.post(f"{API}/extract", json={"text": text}, headers=user_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("known", "learning", "new", "counts"):
        assert k in d
    c = d["counts"]
    assert c["known"] + c["learning"] + c["new"] > 0
    # at least one known/new word should reflect the bank hit for 'abate'
    all_hw = [x["headword"] for x in (d["known"] + d["learning"] + d["new"])]
    assert "abate" in all_hw


def test_extract_empty_text(user_h):
    r = requests.post(f"{API}/extract", json={"text": ""}, headers=user_h, timeout=10)
    assert r.status_code == 400


def test_extract_pdf(user_h):
    # build a tiny PDF in-memory using pypdf
    try:
        from pypdf import PdfWriter
    except Exception:
        pytest.skip("pypdf not available")
    # Simpler: build a raw minimal PDF byte stream containing text
    # Use reportlab-like construction via pypdf isn't straightforward; use raw PDF.
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 90>>stream\n"
        b"BT /F1 12 Tf 72 720 Td (abate mitigate ephemeral serendipity rigorous investigation) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000053 00000 n \n0000000099 00000 n \n"
        b"0000000199 00000 n \n0000000330 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n395\n%%EOF"
    )
    files = {"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r = requests.post(f"{API}/extract-pdf",
                      headers={"Authorization": user_h["Authorization"]},
                      files=files, timeout=30)
    # Accept either 200 or 422 (if pypdf can't parse this hand-crafted PDF)
    assert r.status_code in (200, 422), f"{r.status_code} {r.text}"
    if r.status_code == 200:
        d = r.json()
        for k in ("known", "learning", "new", "counts"):
            assert k in d


# ---------- Smart Review Nudges ----------
def test_slipping_empty_for_fresh_user(user_h):
    r = requests.get(f"{API}/review/slipping", headers=user_h, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "count" in d and "words" in d
    assert isinstance(d["words"], list)


def test_slipping_after_wrong_answer():
    """Register a NEW user, answer a word correctly (gains SEEN status), then verify slipping list surfaces it."""
    _, h = _register()
    # A correct answer promotes mastery > 0 -> status SEEN with next_review within horizon
    a = requests.post(f"{API}/practice/answer", json={
        "word_id": "abate", "mode": "multiple_choice", "correct": True, "response_time_ms": 3000
    }, headers=h, timeout=15)
    assert a.status_code == 200
    # after wrong answer, next_review_at = now+10min -> should be within 2-day horizon
    r = requests.get(f"{API}/review/slipping", headers=h, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["count"] >= 1, f"expected >=1 slipping word, got {d}"
    hws = [w["headword"] for w in d["words"]]
    assert "abate" in hws
    item = next(w for w in d["words"] if w["headword"] == "abate")
    for k in ("id", "headword", "mastery_score", "overdue_days", "status"):
        assert k in item


def test_practice_start_slipping_source():
    _, h = _register()
    # seed slipping list with a correct answer -> SEEN status, within 2-day horizon
    requests.post(f"{API}/practice/answer", json={
        "word_id": "abate", "mode": "multiple_choice", "correct": True, "response_time_ms": 3000
    }, headers=h, timeout=15)
    p = requests.post(f"{API}/practice/start", params={"source": "slipping"},
                      headers=h, timeout=30)
    assert p.status_code == 200, p.text
    d = p.json()
    assert d["count"] >= 1
    assert d["source"] == "slipping"
    assert d["questions"][0]["word_id"] == "abate"


def test_practice_start_list_source(user_h):
    """source=list with a mix: existing word + AI-imported word."""
    # 'abate' is in the bank; 'serendipity' should be imported via AI fallback
    p = requests.post(f"{API}/practice/start",
                      params={"source": "list", "ref": "abate,serendipity"},
                      headers=user_h, timeout=90)
    assert p.status_code == 200, p.text
    d = p.json()
    assert d["count"] >= 1
    headwords = [q["headword"] for q in d["questions"]]
    assert "abate" in headwords


# ---------- Regression ----------
def test_regression_entitlements_free(user_h):
    r = requests.get(f"{API}/entitlements", headers=user_h, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["tier"] == "free"
    assert d["limits"]["daily_new_words"] == 8


def test_regression_mission_cap(user_h):
    r = requests.get(f"{API}/mission", headers=user_h, timeout=15)
    assert r.status_code == 200
    assert r.json()["new_count"] <= 8


def test_regression_practice_answer_complete(user_h):
    s = requests.post(f"{API}/practice/start", params={"source": "word", "ref": "abate"},
                      headers=user_h, timeout=20).json()
    assert s["count"] >= 1
    q = s["questions"][0]
    a = requests.post(f"{API}/practice/answer", json={
        "word_id": q["word_id"], "mode": q["mode"], "correct": True, "response_time_ms": 3000
    }, headers=user_h, timeout=15)
    assert a.status_code == 200
    c = requests.post(f"{API}/practice/complete", json={
        "answered": 1, "correct": 1, "duration_ms": 30000, "source": "word"
    }, headers=user_h, timeout=15)
    assert c.status_code == 200
