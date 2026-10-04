"""Phase E — practice engine tests (pure/deterministic) + API regression."""
import os
import sys
import uuid

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from practice_engine import (  # noqa: E402
    MODES, build_question, generate_question, validate_question,
    select_practice_mode, score_answer, relation_headwords,
)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://vocabist-restore.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _word(**over):
    w = {"id": "abate", "headword": "abate", "canonical_key": "abate",
         "simple_definition": "to become less strong", "part_of_speech": "verb",
         "cefr": "C1", "topic": "academic", "example": "The storm began to abate.",
         "easy_example": "The rain started to abate.",
         "relations": {"synonyms": [{"ref": None, "headword": "lessen"}],
                       "antonyms": [{"ref": "increase", "headword": "increase"}],
                       "related": [], "confusing_words": [],
                       "word_family": ["abatement"], "roots": [], "prefixes": [], "suffixes": []}}
    w.update(over)
    return w


def _pool(n=12):
    pool = [_word()]
    defs = ["a big cat", "to run fast", "a tall tree", "a bright star", "a cold wind",
            "a small dog", "a loud noise", "a calm sea", "a warm fire", "a long road", "a deep hole"]
    pos = ["noun", "verb", "noun", "noun", "noun", "noun", "noun", "noun", "noun", "noun", "noun"]
    for i in range(n):
        pool.append({"id": f"w{i}", "headword": f"word{i}", "canonical_key": f"word{i}",
                     "simple_definition": defs[i % len(defs)], "part_of_speech": pos[i % len(pos)],
                     "cefr": "B1", "topic": "everyday", "example": f"This is word{i} in a sentence.",
                     "relations": {}})
    return pool


# 1. all mode names present
def test_mode_catalog():
    for m in ["multiple_choice", "synonym_select", "antonym_select", "true_false",
              "spelling", "fill_blank", "definition_recall", "sentence_completion",
              "context_choice", "word_usage", "confusing_words", "word_family", "mixed_adaptive"]:
        assert m in MODES


# 2/3/4/5/6/7. contract + determinism + distractors + validity + canonical source
def test_multiple_choice_contract_and_determinism():
    pool = _pool()
    q1 = build_question(_word(), "multiple_choice", pool)
    q2 = build_question(_word(), "multiple_choice", pool)
    assert q1 == q2                                   # deterministic
    for k in ("question_id", "word_id", "mode", "prompt", "options", "answer",
              "correct_answer", "difficulty", "source", "metadata"):
        assert k in q1
    assert q1["source"] == "canonical"
    assert len(q1["options"]) >= 4
    assert len(q1["options"]) == len(set(q1["options"]))   # no dupes
    assert q1["answer"] in q1["options"]                   # correct present
    assert q1["answer"] == "to become less strong"         # canonical definition


# 8/9. synonym + antonym (canonical, no fabrication)
def test_synonym_and_antonym_modes():
    pool = _pool()
    syn = build_question(_word(), "synonym_select", pool)
    ant = build_question(_word(), "antonym_select", pool)
    assert syn and syn["answer"] == "lessen"
    assert ant and ant["answer"] == "increase"
    # no synonyms -> cannot build -> None (never fabricated)
    assert build_question(_word(relations={"synonyms": [], "antonyms": []}), "synonym_select", pool) is None


# 10. true/false
def test_true_false_uses_canonical_facts():
    q = build_question(_word(), "true_false", _pool())
    assert q["options"] == ["True", "False"]
    assert q["answer"] in ("True", "False")


# 11/12. spelling + fill blank
def test_spelling_hides_word_and_fill_blank_removes_word():
    sp = build_question(_word(), "spelling", _pool())
    assert "abate" not in sp["prompt"] and sp["answer"] == "abate" and sp["input"] == "text"
    fb = build_question(_word(), "fill_blank", _pool())
    assert "_____" in fb["prompt"] and fb["answer"] == "abate"


# 13/14/15/16. recall/completion/context/usage
def test_recall_completion_context_usage():
    assert build_question(_word(), "definition_recall", _pool())["input"] == "text"
    assert "_____" in build_question(_word(), "sentence_completion", _pool())["prompt"]
    assert build_question(_word(), "context_choice", _pool())["answer"] == "to become less strong"
    usage = build_question(_word(), "word_usage", _pool())
    assert usage and "abate" in usage["answer"].lower()


# 17/18. confusing words + word family (verified only)
def test_confusing_and_family_require_canonical_data():
    assert build_question(_word(), "confusing_words", _pool()) is None  # none defined -> no fabrication
    w = _word(); w["relations"]["confusing_words"] = [{"ref": None, "headword": "abet"}]
    assert build_question(w, "confusing_words", _pool())["answer"] == "abate"
    fam = build_question(_word(), "word_family", _pool())
    assert fam and fam["answer"] == "abatement"


# 19. mixed adaptive selection deterministic + reason codes
def test_mixed_adaptive_selection():
    m_new, r_new = select_practice_mode(_word(), {"status": "NEW"})
    m_mast, r_mast = select_practice_mode(_word(), {"status": "MASTERED", "mastery_score": 95})
    assert m_new in ("multiple_choice", "true_false", "synonym_select")
    assert "high_recognition" in r_new
    assert "mastery_challenge" in r_mast
    # deterministic
    assert select_practice_mode(_word(), {"status": "NEW"})[0] == m_new


# 20. mode diversity
def test_mode_diversity_avoids_recent():
    m, _ = select_practice_mode(_word(), {"status": "LEARNING"}, session_modes=["multiple_choice", "multiple_choice"])
    assert m != "multiple_choice"


# 21. fallback behavior
def test_generate_question_falls_back():
    # request a mode the word can't support (no confusing words) -> falls back, still valid
    q = generate_question(_word(), _pool(), {"status": "SEEN"}, requested_mode="confusing_words")
    assert q is not None and validate_question(q)
    assert q["metadata"].get("fell_back_from") == "confusing_words"


# 22. malformed content rejection
def test_validation_rejects_malformed():
    assert not validate_question({"word_id": "x", "mode": "multiple_choice", "prompt": "",
                                  "options": ["a", "b", "c", "d"], "answer": "a"})
    assert not validate_question({"word_id": "x", "mode": "multiple_choice", "prompt": "p",
                                  "options": ["a", "a", "b", "c"], "answer": "a"})   # dup
    assert not validate_question({"word_id": "x", "mode": "multiple_choice", "prompt": "p",
                                  "options": ["a", "b", "c", "d"], "answer": "z"})   # answer absent


# 23/24. answer normalization + evaluation
def test_answer_evaluation():
    mc = build_question(_word(), "multiple_choice", _pool())
    assert score_answer(mc, "  To Become Less Strong  ")["correct"] is True
    assert score_answer(mc, "totally wrong")["correct"] is False
    rec = build_question(_word(), "definition_recall", _pool())
    assert score_answer(rec, "become less strong")["correct"] is True     # token overlap, not exact
    sp = build_question(_word(), "spelling", _pool())
    assert score_answer(sp, "ABATE")["correct"] is True
    assert score_answer(sp, "abaet")["correct"] is False


# 25. insufficient pool -> graceful None (no random fabrication)
def test_insufficient_pool_degrades():
    assert build_question(_word(), "multiple_choice", [_word()]) is None  # no distractors


# ---------------------------- API regression ----------------------------
def _headers():
    email = f"phasee_{uuid.uuid4().hex[:10]}@vocabist.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123",
                      "name": "PhaseE"}, timeout=30)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}
    requests.post(f"{API}/onboarding", json={"reason": "IELTS", "level": "B2",
                  "daily_minutes": 10, "exam_slug": "ielts"}, headers=h, timeout=30)
    return h


def test_api_practice_start_and_answer_and_mixed():
    h = _headers()
    ps = requests.post(f"{API}/practice/start?source=mission", headers=h, timeout=30).json()
    assert ps["count"] >= 1
    q = ps["questions"][0]
    for k in ("word_id", "mode", "prompt", "answer", "card"):
        assert k in q
    a = requests.post(f"{API}/practice/answer", json={"word_id": q["word_id"], "mode": q["mode"],
                      "correct": True, "response_time_ms": 3000}, headers=h, timeout=30)
    assert a.status_code == 200 and a.json()["xp_gain"] == 10
    # explicit mode request
    r = requests.post(f"{API}/practice/start?source=word&ref=abate&mode=spelling", headers=h, timeout=30)
    assert r.status_code == 200 and r.json()["count"] >= 1


def test_api_regressions_intact():
    h = _headers()
    assert requests.get(f"{API}/mission", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/progress", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/review/slipping", headers=h, timeout=30).status_code == 200
    assert requests.get(f"{API}/words/abate", headers=h, timeout=30).status_code == 200
    requests.post(f"{API}/words/abate/save", headers=h, timeout=30)
    assert any(w["id"] == "abate" for w in requests.get(f"{API}/saved", headers=h, timeout=30).json()["words"])
    assert requests.post(f"{API}/words/import", json={"headword": "Abate"}, headers=h, timeout=30).json()["id"] == "abate"
