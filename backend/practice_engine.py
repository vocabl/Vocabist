"""Practice engine (Phase E).

Pure, deterministic question generation / selection / validation / scoring built
entirely from canonical vocabulary records. No MongoDB, no AI/LLM, no unseeded
randomness. The caller passes the target word plus a candidate ``pool`` (already
loaded from the DB) so this module stays DB-independent and testable.

Question contract (superset — keeps the legacy keys the app already reads:
``word_id/mode/prompt/options/answer/card/input/hint``):
    {question_id, word_id, headword, mode, prompt, options, answer,
     correct_answer, explanation, difficulty, source, metadata, [input, hint]}

Learner progression stays owned by Phase D (adaptive_learning); this engine only
generates/evaluates questions and reports the result for Phase D to consume.
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

from vocab_schema import normalize_headword

MODES = [
    "multiple_choice", "synonym_select", "antonym_select", "true_false",
    "spelling", "fill_blank", "definition_recall", "sentence_completion",
    "context_choice", "word_usage", "confusing_words", "word_family",
    "mixed_adaptive",
]
OPTION_MODES = {"multiple_choice", "synonym_select", "antonym_select", "true_false",
                "fill_blank", "sentence_completion", "context_choice", "word_usage",
                "confusing_words", "word_family"}
TEXT_MODES = {"spelling", "definition_recall"}
MIN_OPTIONS = 4
CEFR_RANK = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}


# --------------------------------------------------------------------------- #
# canonical helpers
# --------------------------------------------------------------------------- #
def _rng(word_id: str, mode: str) -> random.Random:
    return random.Random(f"{word_id}|{mode}")


def relation_headwords(word: Dict[str, Any], field: str) -> List[str]:
    """Return relation headwords from the canonical relations block, falling
    back to legacy string arrays. Deterministic order, de-duped, self excluded."""
    self_key = normalize_headword(word.get("headword"))
    rels = word.get("relations") if isinstance(word.get("relations"), dict) else {}
    entries = rels.get(field)
    out: List[str] = []
    seen = set()
    if entries is None:
        entries = [{"headword": h} for h in (word.get(field, []) or [])]
    for e in entries:
        hw = e.get("headword") if isinstance(e, dict) else str(e)
        if not hw or not str(hw).strip():
            continue
        k = normalize_headword(hw)
        if not k or k == self_key or k in seen:
            continue
        seen.add(k)
        out.append(str(hw).strip())
    return out


def _definition(word: Dict[str, Any]) -> str:
    if word.get("simple_definition"):
        return word["simple_definition"]
    for m in word.get("meanings", []) or []:
        if m.get("definition"):
            return m["definition"]
    return ""


def _example(word: Dict[str, Any]) -> str:
    for key in ("easy_example", "example"):
        if word.get(key):
            return word[key]
    for m in word.get("meanings", []) or []:
        for ex in m.get("examples", []) or []:
            if ex:
                return ex
    for ex in word.get("contextual_examples", []) or []:
        if ex:
            return ex
    return ""


def pick_distractors(word: Dict[str, Any], pool: List[Dict[str, Any]], n: int,
                     rng: random.Random, value=_definition) -> List[str]:
    """Deterministic distractors preferring same POS, then CEFR proximity, then
    topic. ``value`` extracts the option text (definition or headword)."""
    wid = word.get("id")
    pos = word.get("part_of_speech")
    cefr = CEFR_RANK.get(word.get("cefr"), 3)
    topic = word.get("topic")
    correct_val = value(word)

    def score(w: Dict[str, Any]) -> Tuple:
        return (
            0 if w.get("part_of_speech") == pos else 1,
            abs(CEFR_RANK.get(w.get("cefr"), 3) - cefr),
            0 if w.get("topic") == topic else 1,
        )

    cands = [w for w in pool if w.get("id") != wid]
    rng.shuffle(cands)                      # deterministic tie-break (seeded)
    cands.sort(key=score)
    out: List[str] = []
    used = {normalize_headword(str(correct_val))}
    for w in cands:
        v = value(w)
        if not v:
            continue
        key = normalize_headword(str(v))
        if not key or key in used:
            continue
        used.add(key)
        out.append(v)
        if len(out) >= n:
            break
    return out


# --------------------------------------------------------------------------- #
# question validation
# --------------------------------------------------------------------------- #
def validate_question(q: Optional[Dict[str, Any]]) -> bool:
    if not q or not q.get("word_id") or not q.get("prompt") or not q.get("mode"):
        return False
    answer = q.get("answer")
    if answer is None or str(answer).strip() == "":
        return False
    if q["mode"] in OPTION_MODES:
        opts = q.get("options") or []
        norm = [normalize_headword(str(o)) for o in opts]
        if any(not o for o in norm):
            return False                      # empty option
        if len(norm) != len(set(norm)):
            return False                      # duplicate options
        need = 2 if q["mode"] == "true_false" else MIN_OPTIONS
        if len(opts) < need:
            return False
        if normalize_headword(str(answer)) not in norm:
            return False                      # correct answer absent
    return True


# --------------------------------------------------------------------------- #
# per-mode builders → dict or None (None = cannot build from canonical content)
# --------------------------------------------------------------------------- #
def _base(word: Dict[str, Any], mode: str) -> Dict[str, Any]:
    return {"question_id": f"{word['id']}:{mode}", "word_id": word["id"],
            "headword": word["headword"], "mode": mode,
            "phonetic": word.get("phonetic"), "part_of_speech": word.get("part_of_speech"),
            "source": "canonical", "explanation": _definition(word), "metadata": {}}


def _finish(q: Dict[str, Any], answer, options=None) -> Dict[str, Any]:
    q["answer"] = answer
    q["correct_answer"] = answer
    if options is not None:
        q["options"] = options
    return q


def _mc(word, pool, rng):
    correct = _definition(word)
    if not correct:
        return None
    ds = pick_distractors(word, pool, 3, rng, value=_definition)
    if len(ds) < 3:
        return None
    opts = [correct] + ds
    rng.shuffle(opts)
    q = _base(word, "multiple_choice")
    q["prompt"] = f"What does \u201c{word['headword']}\u201d mean?"
    return _finish(q, correct, opts)


def _relation_select(word, pool, rng, field, mode, label):
    targets = relation_headwords(word, field)
    if not targets:
        return None
    correct = targets[0]
    ds = pick_distractors(word, pool, 3, rng, value=lambda w: w.get("headword"))
    ds = [d for d in ds if normalize_headword(d) != normalize_headword(correct)]
    if len(ds) < 3:
        return None
    opts = [correct] + ds[:3]
    rng.shuffle(opts)
    q = _base(word, mode)
    q["prompt"] = f"Which word is {label} of \u201c{word['headword']}\u201d?"
    return _finish(q, correct, opts)


def _true_false(word, pool, rng):
    correct_def = _definition(word)
    if not correct_def:
        return None
    show_true = rng.random() > 0.5
    if show_true:
        shown, answer = correct_def, "True"
    else:
        ds = pick_distractors(word, pool, 1, rng, value=_definition)
        if not ds:
            return None
        shown, answer = ds[0], "False"
    q = _base(word, "true_false")
    q["prompt"] = f"\u201c{word['headword']}\u201d means: {shown}"
    return _finish(q, answer, ["True", "False"])


def _spelling(word, pool, rng):
    d = _definition(word)
    if not d:
        return None
    q = _base(word, "spelling")
    q["prompt"] = f"Spell the word that means: {d}"
    q["input"] = "text"
    hw = word["headword"]
    q["hint"] = hw[0] + "\u2022" * (len(hw) - 1)
    return _finish(q, hw, [])


def _fill_blank(word, pool, rng, mode="fill_blank"):
    example = _example(word)
    if not example or not re.search(re.escape(word["headword"]), example, re.IGNORECASE):
        return None
    blanked = re.sub(re.escape(word["headword"]), "_____", example, flags=re.IGNORECASE)
    ds = pick_distractors(word, pool, 3, rng, value=lambda w: w.get("headword"))
    if len(ds) < 3:
        return None
    opts = [word["headword"]] + ds[:3]
    rng.shuffle(opts)
    q = _base(word, mode)
    verb = "Fill the blank" if mode == "fill_blank" else "Which word completes the sentence"
    q["prompt"] = f"{verb}:\n{blanked}"
    return _finish(q, word["headword"], opts)


def _definition_recall(word, pool, rng):
    d = _definition(word)
    if not d:
        return None
    q = _base(word, "definition_recall")
    q["prompt"] = f"What does \u201c{word['headword']}\u201d mean? (type the meaning)"
    q["input"] = "text"
    return _finish(q, d, [])


def _context_choice(word, pool, rng):
    example = _example(word)
    correct = _definition(word)
    if not example or not correct:
        return None
    ds = pick_distractors(word, pool, 3, rng, value=_definition)
    if len(ds) < 3:
        return None
    opts = [correct] + ds
    rng.shuffle(opts)
    q = _base(word, "context_choice")
    shown = re.sub(re.escape(word["headword"]), word["headword"], example, flags=re.IGNORECASE)
    q["prompt"] = f"In this sentence, what does \u201c{word['headword']}\u201d mean?\n\u201c{shown}\u201d"
    return _finish(q, correct, opts)


def _word_usage(word, pool, rng):
    correct = _example(word)
    if not correct or not re.search(re.escape(word["headword"]), correct, re.IGNORECASE):
        return None
    # distractor sentences: other words' examples (they correctly use OTHER words,
    # so they do not correctly use the target word). Deterministic, no fabrication.
    others = [w for w in pool if w.get("id") != word["id"] and _example(w)
              and not re.search(re.escape(word["headword"]), _example(w), re.IGNORECASE)]
    rng.shuffle(others)
    ds = [_example(w) for w in others[:3]]
    if len(ds) < 3:
        return None
    opts = [correct] + ds
    rng.shuffle(opts)
    q = _base(word, "word_usage")
    q["prompt"] = f"Which sentence uses \u201c{word['headword']}\u201d correctly?"
    return _finish(q, correct, opts)


def _confusing_words(word, pool, rng):
    targets = relation_headwords(word, "confusing_words")
    if not targets:
        return None
    d = _definition(word)
    if not d:
        return None
    ds = targets[:3]
    extra = pick_distractors(word, pool, 3 - len(ds), rng, value=lambda w: w.get("headword")) if len(ds) < 3 else []
    opts = [word["headword"]] + ds + extra
    # de-dup preserve order
    seen, clean = set(), []
    for o in opts:
        k = normalize_headword(o)
        if k and k not in seen:
            seen.add(k); clean.append(o)
    if len(clean) < MIN_OPTIONS:
        return None
    rng.shuffle(clean)
    q = _base(word, "confusing_words")
    q["prompt"] = f"Which word means: {d}?"
    q["metadata"]["confusing_with"] = targets
    return _finish(q, word["headword"], clean)


def _word_family(word, pool, rng):
    family = [f for f in (relation_headwords(word, "word_family")) if normalize_headword(f) != normalize_headword(word["headword"])]
    if not family:
        return None
    correct = family[0]
    ds = pick_distractors(word, pool, 3, rng, value=lambda w: w.get("headword"))
    ds = [d for d in ds if normalize_headword(d) != normalize_headword(correct)]
    if len(ds) < 3:
        return None
    opts = [correct] + ds[:3]
    rng.shuffle(opts)
    q = _base(word, "word_family")
    q["prompt"] = f"Which word belongs to the same word family as \u201c{word['headword']}\u201d?"
    return _finish(q, correct, opts)


_BUILDERS = {
    "multiple_choice": _mc,
    "synonym_select": lambda w, p, r: _relation_select(w, p, r, "synonyms", "synonym_select", "a synonym"),
    "antonym_select": lambda w, p, r: _relation_select(w, p, r, "antonyms", "antonym_select", "an antonym"),
    "true_false": _true_false,
    "spelling": _spelling,
    "fill_blank": _fill_blank,
    "definition_recall": _definition_recall,
    "sentence_completion": lambda w, p, r: _fill_blank(w, p, r, mode="sentence_completion"),
    "context_choice": _context_choice,
    "word_usage": _word_usage,
    "confusing_words": _confusing_words,
    "word_family": _word_family,
}


def build_question(word: Dict[str, Any], mode: str, pool: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build one validated question, or None if the canonical content can't
    support this mode (caller should fall back)."""
    builder = _BUILDERS.get(mode)
    if not builder:
        return None
    q = builder(word, pool, _rng(word["id"], mode))
    if q is None or not validate_question(q):
        return None
    q.setdefault("difficulty", 0.5)
    return q


# --------------------------------------------------------------------------- #
# adaptive mode selection + fallback
# --------------------------------------------------------------------------- #
def _last_result(progress: Dict[str, Any]) -> Optional[int]:
    recent = (progress or {}).get("recent_results") or []
    if recent:
        return recent[-1]
    if (progress or {}).get("times_seen"):
        return 1 if (progress or {}).get("consecutive_correct", 0) > 0 else 0
    return None


def select_practice_mode(word: Dict[str, Any], progress: Optional[Dict[str, Any]],
                         session_modes: Optional[List[str]] = None) -> Tuple[str, List[str]]:
    """Deterministically choose a concrete mode from learner state (Phase D
    signals) + available canonical content. Returns (mode, reason_codes)."""
    progress = progress or {}
    session_modes = session_modes or []
    status = progress.get("status", "NEW")
    mastery = float(progress.get("mastery_score", 0))
    last = _last_result(progress)
    reasons: List[str] = []

    has_conf = bool(relation_headwords(word, "confusing_words"))
    tiers: List[str]
    if status in ("NEW", "SEEN"):
        reasons.append("high_recognition")
        tiers = ["multiple_choice", "true_false", "synonym_select"]
    elif status == "LEARNING":
        reasons.append("weak_recall")
        tiers = ["multiple_choice", "true_false", "fill_blank", "synonym_select"]
    elif status == "RECALLING":
        reasons.append("needs_context")
        tiers = ["definition_recall", "spelling", "fill_blank", "sentence_completion", "context_choice"]
    else:  # MASTERED
        reasons.append("mastery_challenge")
        tiers = ["context_choice", "word_usage", "word_family", "sentence_completion", "definition_recall"]

    if has_conf and last == 0:
        reasons.append("confusing_pair")
        tiers = ["confusing_words"] + tiers
    if last == 0 and mastery < 40:
        reasons.append("recent_error")
        tiers = ["multiple_choice"] + tiers

    # prefer a mode not just used, when an equally-valid alternative exists
    ordered = [m for m in tiers if m not in session_modes[-2:]] + tiers
    for m in ordered:
        if m not in reasons:  # guard: reasons list is codes, not modes
            pass
    return ordered[0] if ordered else "multiple_choice", reasons


# canonical fallback order when the chosen mode can't be built
_FALLBACK_ORDER = ["multiple_choice", "true_false", "fill_blank", "spelling",
                   "definition_recall", "synonym_select", "context_choice"]


def generate_question(word: Dict[str, Any], pool: List[Dict[str, Any]],
                      progress: Optional[Dict[str, Any]] = None,
                      requested_mode: Optional[str] = None,
                      session_modes: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Resolve the mode (respecting an explicit request; ``mixed_adaptive``/None
    → adaptive selection), build it, and gracefully fall back through other
    valid modes. Returns a validated question or None if nothing can be built."""
    reasons: List[str] = []
    if requested_mode and requested_mode not in ("mixed_adaptive", None):
        first = requested_mode
    else:
        first, reasons = select_practice_mode(word, progress, session_modes)

    tried = []
    order = [first] + [m for m in _FALLBACK_ORDER if m != first]
    for mode in order:
        tried.append(mode)
        q = build_question(word, mode, pool)
        if q:
            q["difficulty"] = round(float((progress or {}).get("difficulty", 0.5) or 0.5), 3)
            q["metadata"]["reason_codes"] = reasons
            q["metadata"]["selected_mode"] = q["mode"]
            if len(tried) > 1:
                q["metadata"]["fell_back_from"] = first
            return q
    return None


# --------------------------------------------------------------------------- #
# answer evaluation
# --------------------------------------------------------------------------- #
def _norm_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def score_answer(question: Dict[str, Any], answer: str,
                 response_time_ms: int = 0) -> Dict[str, Any]:
    """Deterministic evaluation. Option modes → normalized equality. Spelling →
    normalized exact word. definition_recall → token-overlap (≥0.6) so exact
    wording isn't required. No LLM."""
    mode = question.get("mode")
    correct = str(question.get("answer", ""))
    na = _norm_text(answer)
    nc = _norm_text(correct)
    reasons: List[str] = []

    if mode == "definition_recall":
        ct = set(nc.split())
        at = set(na.split())
        overlap = len(ct & at) / len(ct) if ct else 0.0
        ok = na == nc or (len(na) >= 3 and overlap >= 0.6)
        reasons.append("meaning_match" if ok else "meaning_mismatch")
    elif mode in TEXT_MODES:  # spelling
        ok = na == nc
        reasons.append("correct_spelling" if ok else "spelling_error")
    else:
        ok = na == nc
        reasons.append("correct_option" if ok else "wrong_option")

    return {"correct": bool(ok), "normalized_answer": na,
            "response_time_ms": response_time_ms, "reason_codes": reasons}
