"""Phase D — adaptive learning engine tests.

Pure deterministic unit tests for backend/adaptive_learning.py plus API
no-regression checks against the running backend.
"""
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from adaptive_learning import (  # noqa: E402
    normalize_response_time,
    calculate_mastery_update,
    calculate_confidence_update,
    calculate_difficulty,
    calculate_learning_state,
    calculate_next_review,
    select_learning_priority,
    calculate_slipping,
    update_progress,
    INTERVAL_MAX_DAYS,
)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://vocabist-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _apply(prev, correct, rt=3000, meta=None, now=NOW):
    return update_progress(prev, correct, rt, meta or {"cefr": "B1"}, now)


# 1. new word
def test_new_word_defaults():
    p = _apply(None, True)
    assert p["times_seen"] == 1 and p["times_correct"] == 1
    assert p["status"] in ("SEEN", "LEARNING")  # never MASTERED on first answer
    assert 0 <= p["mastery_score"] <= 100


# 2/3. first correct / incorrect
def test_first_correct_and_incorrect():
    c = _apply(None, True)
    w = _apply(None, False)
    assert c["mastery_score"] > 0 and c["consecutive_correct"] == 1
    assert w["mastery_score"] == 0 and w["consecutive_correct"] == 0
    assert w["status"] == "SEEN"


# 4. repeated correct -> mastery climbs, diminishing, can reach MASTERED
def test_repeated_correct_reaches_mastery():
    p = None
    for _ in range(11):
        p = _apply(p, True, rt=2000)
    assert p["status"] == "MASTERED"
    assert p["mastery_score"] >= 85 and p["confidence_score"] >= 80


# 5. repeated incorrect -> stays low
def test_repeated_incorrect_stays_low():
    p = None
    for _ in range(4):
        p = _apply(p, False)
    assert p["mastery_score"] == 0
    assert p["status"] in ("SEEN",)


# 6/7/8. bounds
def test_bounds_respected():
    assert calculate_mastery_update(100, True, 30, 1.0) <= 100
    assert calculate_mastery_update(0, False, 0, 0.2) >= 0
    assert calculate_confidence_update(100, True, 9, 1.0, False) <= 100
    assert calculate_confidence_update(0, False, 0, 0.2, True) >= 0
    assert 0 <= calculate_difficulty(5, 5, 0, 0, 0.2, {}) <= 1
    assert 0 <= calculate_difficulty(0, 0, 0, 0, None, {"cefr": "C2"}) <= 1


# 9. interval growth
def test_interval_grows_with_consecutive():
    d1, _ = calculate_next_review(True, 1, 60, 70, 0.4, NOW)
    d3, _ = calculate_next_review(True, 3, 60, 70, 0.4, NOW)
    d6, _ = calculate_next_review(True, 6, 80, 85, 0.3, NOW)
    assert d1 < d3 < d6 <= INTERVAL_MAX_DAYS


# 10. interval contraction after failure
def test_interval_contracts_on_failure():
    days, nxt = calculate_next_review(False, 0, 40, 40, 0.6, NOW)
    assert days == 0
    assert nxt < NOW + timedelta(hours=1)


# 11/12/13. priority signals
def test_priority_overdue_low_conf_recent_error():
    overdue = {"next_review_at": NOW - timedelta(days=5), "mastery_score": 40,
               "confidence_score": 30, "status": "LEARNING", "recent_results": [0]}
    fresh = {"next_review_at": NOW + timedelta(days=5), "mastery_score": 90,
             "confidence_score": 90, "status": "MASTERED", "recent_results": [1]}
    po = select_learning_priority(overdue, {}, NOW)
    pf = select_learning_priority(fresh, {}, NOW)
    assert po["priority"] > pf["priority"]
    assert "overdue" in po["reason_codes"]
    assert "low_confidence" in po["reason_codes"]
    assert "recent_error" in po["reason_codes"]


def test_exam_relevance_does_not_override_evidence():
    weak = {"next_review_at": NOW - timedelta(days=4), "mastery_score": 20,
            "confidence_score": 20, "status": "LEARNING", "recent_results": [0]}
    strong_exam = {"next_review_at": NOW + timedelta(days=10), "mastery_score": 95,
                   "confidence_score": 95, "status": "MASTERED", "recent_results": [1]}
    pw = select_learning_priority(weak, {}, NOW)
    pe = select_learning_priority(strong_exam, {"exam_relevance": ["ielts"]}, NOW, active_exam="ielts")
    assert pw["priority"] > pe["priority"]  # evidence beats exam boost


# 14/15. mastered stability + failure recovery
def test_mastered_stability_and_recovery():
    p = None
    for _ in range(11):
        p = _apply(p, True, rt=2000)
    assert p["status"] == "MASTERED"
    before = p["mastery_score"]
    p2 = _apply(p, False)
    assert p2["mastery_score"] < before                       # dropped
    assert p2["mastery_score"] > 0                            # not destroyed
    assert p2["status"] in ("RECALLING", "LEARNING")          # demoted, not reset


# 16/17. response time effects
def test_response_time_effect_and_sparse_history():
    fast = calculate_mastery_update(50, True, 3, 0.9)
    slow = calculate_mastery_update(50, True, 3, 0.35)
    assert fast > slow
    assert normalize_response_time(3000, 0, 0) == 0.6 + (0.85 - 0.6) * 0.5  # sparse -> conservative
    assert normalize_response_time(None, 5000, 5) is None
    assert normalize_response_time(2000, 8000, 5) == 0.9   # much faster than personal avg


# 18. slipping
def test_slipping_detection():
    slipping = {"review_interval": 16, "mastery_score": 55, "confidence_score": 40,
                "recent_results": [1, 1, 0], "next_review_at": NOW - timedelta(days=1)}
    stable = {"review_interval": 30, "mastery_score": 95, "confidence_score": 92,
              "recent_results": [1, 1, 1], "next_review_at": NOW + timedelta(days=20)}
    s1 = calculate_slipping(slipping, NOW)
    s2 = calculate_slipping(stable, NOW)
    assert s1["slipping_score"] > s2["slipping_score"]
    assert "failed_after_long_interval" in s1["reason_codes"]


# 19. determinism
def test_deterministic_repeated_calls():
    a = _apply({"times_seen": 3, "times_correct": 2, "times_wrong": 1,
                "consecutive_correct": 2, "mastery_score": 50, "confidence_score": 45,
                "average_response_time": 4000, "review_interval": 3,
                "recent_results": [1, 0, 1], "status": "LEARNING"}, True, rt=3500)
    b = _apply({"times_seen": 3, "times_correct": 2, "times_wrong": 1,
                "consecutive_correct": 2, "mastery_score": 50, "confidence_score": 45,
                "average_response_time": 4000, "review_interval": 3,
                "recent_results": [1, 0, 1], "status": "LEARNING"}, True, rt=3500)
    a.pop("last_reviewed_at"); a.pop("next_review_at"); a.pop("updated_at")
    b.pop("last_reviewed_at"); b.pop("next_review_at"); b.pop("updated_at")
    assert a == b


# 20. missing optional fields / defaults
def test_missing_optional_fields_default_safely():
    p = update_progress({"times_seen": 2, "mastery_score": 30}, True, 0, None, NOW)
    assert "difficulty" in p and 0 <= p["difficulty"] <= 1
    assert p["recent_results"][-1] == 1
    assert p["status"] in ("SEEN", "LEARNING", "RECALLING", "MASTERED")


# ---------------------------- API regression ----------------------------
def _headers():
    email = f"phased_{uuid.uuid4().hex[:10]}@vocabist.app"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123", "name": "PhaseD"}, timeout=30)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}
    requests.post(f"{API}/onboarding", json={"reason": "IELTS", "level": "B2",
                  "daily_minutes": 10, "exam_slug": "ielts"}, headers=h, timeout=30)
    return h


def test_api_answer_and_mission_and_progress():
    h = _headers()
    ps = requests.post(f"{API}/practice/start?source=mission", headers=h, timeout=30).json()
    assert ps["count"] >= 1
    wid = ps["questions"][0]["word_id"]
    a = requests.post(f"{API}/practice/answer", json={"word_id": wid, "mode": "multiple_choice",
                      "correct": True, "response_time_ms": 3000}, headers=h, timeout=30)
    assert a.status_code == 200
    body = a.json()
    assert body["xp_gain"] == 10
    assert body["status"] in ("SEEN", "LEARNING", "RECALLING", "MASTERED")
    assert "confidence_score" in body and "difficulty" in body and "reason_codes" in body
    assert "next_review_at" in body
    assert requests.get(f"{API}/mission", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/progress", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/review/slipping", headers=h, timeout=30).status_code == 200


def test_api_word_detail_saved_import_unaffected():
    h = _headers()
    assert requests.get(f"{API}/words/abate", headers=h, timeout=30).status_code == 200
    requests.post(f"{API}/words/abate/save", headers=h, timeout=30)
    assert any(w["id"] == "abate" for w in requests.get(f"{API}/saved", headers=h, timeout=30).json()["words"])
    assert requests.post(f"{API}/words/import", json={"headword": "Abate"}, headers=h, timeout=30).json()["id"] == "abate"
