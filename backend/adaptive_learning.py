"""Adaptive learning engine (Phase D).

Pure, deterministic, DB-free learning logic. No MongoDB access, no AI/LLM, no
randomness — the same inputs always produce the same outputs, and every decision
carries explainable ``reason_codes``.

Vocabulary of scores:
    mastery_score   0..100  demonstrated retention (how well recalled)
    confidence_score 0..100 reliability/consistency of that evidence
    difficulty      0..1    learner-specific difficulty (NOT the same as CEFR)
    priority        0..1    how much this word deserves study right now
    slipping_score  0..1    evidence that retention is weakening

Statuses (unchanged): NEW, SEEN, LEARNING, RECALLING, MASTERED.

Timezone: all datetimes are treated as timezone-aware UTC. Naive inputs are
coerced to UTC. User-local timezones are out of scope for this phase (documented
limitation) — UTC is used consistently.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---- bounds & constants (documented) ----------------------------------------
MASTERY_MIN, MASTERY_MAX = 0.0, 100.0
CONFIDENCE_MIN, CONFIDENCE_MAX = 0.0, 100.0
DIFFICULTY_MIN, DIFFICULTY_MAX = 0.0, 1.0
INTERVAL_MIN_DAYS = 1
INTERVAL_MAX_DAYS = 180
FAIL_RELEARN_MINUTES = 10
RECENT_WINDOW = 10  # rolling accuracy window kept on the progress doc

# interval growth by consecutive_correct (index capped). Explainable, not SM-2.
INTERVAL_BASE_DAYS = [1, 1, 2, 4, 8, 16, 32, 60, 100, 180]

CEFR_RANK = {"A1": 0, "A2": 1, "B1": 2, "B2": 3, "C1": 4, "C2": 5}

STATUS_WEIGHT = {"NEW": 0.50, "SEEN": 0.55, "LEARNING": 0.72,
                 "RECALLING": 0.60, "MASTERED": 0.20}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# --------------------------------------------------------------------------- #
# response time
# --------------------------------------------------------------------------- #
def normalize_response_time(rt_ms: Optional[int], avg_rt_ms: Optional[float],
                            times_seen: int) -> Optional[float]:
    """Return a speed signal in ~[0.2, 0.95] (1 = fast/confident) or None.

    Compares against the learner's own average when history exists; otherwise
    falls back to absolute thresholds. Sparse history is weighted conservatively
    (pulled toward the neutral 0.6). Missing/invalid time → None (signal omitted).
    """
    if not rt_ms or rt_ms <= 0:
        return None
    if avg_rt_ms and avg_rt_ms > 0 and times_seen >= 2:
        ratio = rt_ms / avg_rt_ms
        if ratio <= 0.8:
            speed = 0.9
        elif ratio <= 1.3:
            speed = 0.6
        elif ratio <= 2.0:
            speed = 0.4
        else:
            speed = 0.25
    else:
        # absolute fallback (no reliable personal baseline yet)
        if rt_ms < 4000:
            speed = 0.85
        elif rt_ms < 8000:
            speed = 0.6
        else:
            speed = 0.35
        if times_seen < 2:  # conservative when history is sparse
            speed = 0.6 + (speed - 0.6) * 0.5
    return round(speed, 3)


# --------------------------------------------------------------------------- #
# mastery & confidence
# --------------------------------------------------------------------------- #
def calculate_mastery_update(mastery: float, correct: bool, prev_interval_days: int,
                             speed: Optional[float]) -> float:
    """Bounded 0..100. Correct → gain with diminishing returns (smaller as
    mastery rises) weighted by answer speed, plus a small bonus for succeeding
    after a long interval. Wrong → a meaningful but capped drop (a single miss
    never destroys mastery; a single hit never creates it)."""
    s = 0.6 if speed is None else speed
    if correct:
        diminish = 1.0 - (mastery / 100.0) * 0.75            # 1.0 → 0.25
        speed_w = 0.7 + 0.3 * s                               # 0.775 → 0.985
        interval_bonus = 3.0 if prev_interval_days and prev_interval_days >= 7 else 0.0
        gain = 12.0 * diminish * speed_w + interval_bonus
        return round(_clamp(mastery + gain, MASTERY_MIN, MASTERY_MAX), 1)
    loss = 12.0 + 0.13 * mastery                              # 12 → 25
    return round(_clamp(mastery - loss, MASTERY_MIN, MASTERY_MAX), 1)


def calculate_confidence_update(confidence: float, correct: bool, consecutive_correct: int,
                                speed: Optional[float], was_mastered: bool) -> float:
    """Bounded 0..100. Rises with consistent, stable-speed correct recalls
    (diminishing near the top); falls on mistakes, harder when a previously
    mastered word fails."""
    s = 0.6 if speed is None else speed
    if correct:
        gain = 8.0 + min(consecutive_correct, 5) * 1.2 + (s - 0.6) * 8.0
        gain *= (1.0 - confidence / 130.0)
        return round(_clamp(confidence + gain, CONFIDENCE_MIN, CONFIDENCE_MAX), 1)
    drop = 18.0 + (10.0 if was_mastered else 0.0)
    if s < 0.4:  # a slow miss is weaker/less reliable evidence but still a miss
        drop += 4.0
    return round(_clamp(confidence - drop, CONFIDENCE_MIN, CONFIDENCE_MAX), 1)


# --------------------------------------------------------------------------- #
# difficulty
# --------------------------------------------------------------------------- #
def _difficulty_prior(word_meta: Dict[str, Any]) -> float:
    cefr = (word_meta or {}).get("cefr")
    if cefr in CEFR_RANK:
        prior = 0.3 + 0.45 * (CEFR_RANK[cefr] / 5.0)
    else:
        prior = 0.5
    return _clamp(prior, 0.2, 0.8)


def calculate_difficulty(times_seen: int, times_wrong: int, mastery: float,
                         confidence: float, speed: Optional[float],
                         word_meta: Optional[Dict[str, Any]]) -> float:
    """Learner-specific difficulty 0..1. With <2 exposures uses a deterministic
    prior from vocabulary metadata (CEFR); otherwise blends observed evidence
    (error rate, low mastery/confidence, slowness) with a light metadata prior.
    CEFR alone never dictates difficulty once evidence exists."""
    prior = _difficulty_prior(word_meta or {})
    if times_seen < 2:
        return round(_clamp(prior, DIFFICULTY_MIN, DIFFICULTY_MAX), 3)
    s = 0.6 if speed is None else speed
    error_rate = times_wrong / max(times_seen, 1)
    d = (0.45 * error_rate + 0.25 * (1 - mastery / 100.0)
         + 0.15 * (1 - confidence / 100.0) + 0.15 * (1 - s))
    d = 0.8 * d + 0.2 * prior
    return round(_clamp(d, DIFFICULTY_MIN, DIFFICULTY_MAX), 3)


# --------------------------------------------------------------------------- #
# status transitions
# --------------------------------------------------------------------------- #
def calculate_learning_state(mastery: float, confidence: float,
                             consecutive_correct: int, times_seen: int) -> str:
    """Deterministic status thresholds (documented):
      MASTERED : mastery>=85 AND confidence>=80 AND consecutive_correct>=4
      RECALLING: mastery>=55
      LEARNING : mastery>=25
      SEEN     : attempted at least once (mastery>0 or times_seen>=1)
      NEW      : never attempted
    A mastered word that fails loses mastery/consecutive and demotes to
    RECALLING (moderate failure) or LEARNING (severe)."""
    if times_seen <= 0:
        return "NEW"
    if mastery >= 85 and confidence >= 80 and consecutive_correct >= 4:
        return "MASTERED"
    if mastery >= 55:
        return "RECALLING"
    if mastery >= 25:
        return "LEARNING"
    return "SEEN"


# --------------------------------------------------------------------------- #
# review interval
# --------------------------------------------------------------------------- #
def calculate_next_review(correct: bool, consecutive_correct: int, mastery: float,
                          confidence: float, difficulty: float,
                          now: datetime) -> Tuple[int, datetime]:
    """Adaptive interval (days) + next_review_at (aware UTC).

    Failure → relearn in minutes (interval 0). Success → base growth by
    consecutive_correct, scaled up by mastery+confidence and down by difficulty,
    with a low-confidence cap; clamped to [1, 180] days."""
    now = _ensure_aware(now)
    if not correct:
        return 0, now + timedelta(minutes=FAIL_RELEARN_MINUTES)
    base = INTERVAL_BASE_DAYS[min(consecutive_correct, len(INTERVAL_BASE_DAYS) - 1)]
    strength = 0.6 + (mastery / 100.0) * 0.5 + (confidence / 100.0) * 0.4   # 0.6..1.5
    diff_mult = 1.2 - 0.5 * difficulty                                       # 0.7..1.2
    interval = base * strength * diff_mult
    if confidence < 40:
        interval = min(interval, 2)   # shaky evidence → keep it close
    days = int(round(_clamp(interval, INTERVAL_MIN_DAYS, INTERVAL_MAX_DAYS)))
    return days, now + timedelta(days=days)


# --------------------------------------------------------------------------- #
# priority & slipping
# --------------------------------------------------------------------------- #
def _last_result(progress: Dict[str, Any]) -> Optional[int]:
    recent = progress.get("recent_results") or []
    if recent:
        return recent[-1]
    if progress.get("times_seen"):
        return 1 if progress.get("consecutive_correct", 0) > 0 else 0
    return None


def _overdue_days(progress: Dict[str, Any], now: datetime) -> float:
    nr = _ensure_aware(progress.get("next_review_at"))
    if not nr:
        return 0.0
    return max(0.0, (now - nr).total_seconds() / 86400.0)


def select_learning_priority(progress: Dict[str, Any], word_meta: Optional[Dict[str, Any]],
                             now: datetime, active_exam: Optional[str] = None) -> Dict[str, Any]:
    """Priority 0..1 for study selection, with reason codes. Exam relevance only
    nudges (capped) — it can never override learner evidence."""
    now = _ensure_aware(now)
    mastery = float(progress.get("mastery_score", 0))
    confidence = float(progress.get("confidence_score", 0))
    status = progress.get("status", "NEW")
    overdue = _overdue_days(progress, now)
    overdue_factor = overdue / (overdue + 3.0)                # saturating 0..1
    weakness = 1.0 - mastery / 100.0
    low_conf = 1.0 - confidence / 100.0
    recent_error = 1.0 if _last_result(progress) == 0 else 0.0
    status_w = STATUS_WEIGHT.get(status, 0.5)
    exam_boost = 1.0 if (active_exam and active_exam in (word_meta or {}).get("exam_relevance", [])) else 0.0

    priority = (0.32 * overdue_factor + 0.24 * weakness + 0.16 * low_conf
                + 0.12 * recent_error + 0.10 * status_w + 0.06 * exam_boost)
    priority = round(_clamp(priority, 0.0, 1.0), 3)

    reasons: List[str] = []
    if overdue_factor > 0.5:
        reasons.append("overdue")
    elif overdue_factor > 0:
        reasons.append("review_due")
    if weakness >= 0.6:
        reasons.append("weak_mastery")
    if low_conf >= 0.6:
        reasons.append("low_confidence")
    if recent_error:
        reasons.append("recent_error")
    if status in ("LEARNING", "RECALLING"):
        reasons.append("in_progress")
    if exam_boost:
        reasons.append("exam_relevant")
    if mastery >= 85 and confidence >= 80:
        reasons.append("stable")
    return {"priority": priority, "reason_codes": reasons}


def calculate_slipping(progress: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Slipping score 0..1 (retention weakening), with reason codes."""
    now = _ensure_aware(now)
    mastery = float(progress.get("mastery_score", 0))
    confidence = float(progress.get("confidence_score", 0))
    interval = int(progress.get("review_interval", 0) or 0)
    recent = progress.get("recent_results") or []
    last = _last_result(progress)

    failed_after_long = 1.0 if (last == 0 and interval >= 7) else 0.0
    conf_gap = 1.0 if (confidence < 50 and mastery >= 50) else 0.0
    if recent:
        recent_error_rate = sum(1 for r in recent[-5:] if r == 0) / min(len(recent), 5)
    else:
        recent_error_rate = 0.0
    overdue = _overdue_days(progress, now)
    overdue_factor = overdue / (overdue + 5.0)

    score = (0.4 * failed_after_long + 0.25 * conf_gap
             + 0.2 * recent_error_rate + 0.15 * overdue_factor)
    score = round(_clamp(score, 0.0, 1.0), 3)

    reasons: List[str] = []
    if failed_after_long:
        reasons.append("failed_after_long_interval")
    if conf_gap:
        reasons.append("confidence_drop")
    if recent_error_rate >= 0.5:
        reasons.append("repeated_recent_errors")
    if overdue_factor > 0.5:
        reasons.append("overdue")
    return {"slipping_score": score, "reason_codes": reasons}


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
def update_progress(prev: Optional[Dict[str, Any]], correct: bool, response_time_ms: int,
                    word_meta: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Compute the full updated, explainable progress state after one answer.

    Returns all legacy ``user_word_progress`` fields (so existing readers keep
    working) plus additive ``difficulty``, ``recent_results`` and
    ``last_reason_codes``. Backward-compatible: missing fields on ``prev``
    default safely."""
    now = _ensure_aware(now) or datetime.now(timezone.utc)
    p = prev or {}
    times_seen = int(p.get("times_seen", 0)) + 1
    times_correct = int(p.get("times_correct", 0)) + (1 if correct else 0)
    times_wrong = int(p.get("times_wrong", 0)) + (0 if correct else 1)
    consecutive = int(p.get("consecutive_correct", 0)) + 1 if correct else 0
    prev_interval = int(p.get("review_interval", 0) or 0)
    was_mastered = p.get("status") == "MASTERED"
    prev_avg_rt = p.get("average_response_time", 0) or 0

    speed = normalize_response_time(response_time_ms, prev_avg_rt, int(p.get("times_seen", 0)))

    mastery = calculate_mastery_update(float(p.get("mastery_score", 0)), correct, prev_interval, speed)
    confidence = calculate_confidence_update(float(p.get("confidence_score", 0)), correct,
                                             consecutive, speed, was_mastered)
    difficulty = calculate_difficulty(times_seen, times_wrong, mastery, confidence, speed, word_meta)
    status = calculate_learning_state(mastery, confidence, consecutive, times_seen)
    interval_days, next_review = calculate_next_review(correct, consecutive, mastery,
                                                       confidence, difficulty, now)

    if response_time_ms and response_time_ms > 0:
        avg_rt = response_time_ms if not prev_avg_rt else int((prev_avg_rt * 2 + response_time_ms) / 3)
    else:
        avg_rt = prev_avg_rt

    recent = list(p.get("recent_results") or [])
    recent.append(1 if correct else 0)
    recent = recent[-RECENT_WINDOW:]

    reason_codes: List[str] = []
    reason_codes.append("recent_success" if correct else "recent_failure")
    if correct and prev_interval >= 7:
        reason_codes.append("recalled_after_long_interval")
    if was_mastered and not correct:
        reason_codes.append("mastered_word_failed")
    if confidence < 40:
        reason_codes.append("low_confidence")
    elif confidence >= 80:
        reason_codes.append("high_confidence")

    return {
        "times_seen": times_seen,
        "times_correct": times_correct,
        "times_wrong": times_wrong,
        "consecutive_correct": consecutive,
        "mastery_score": mastery,
        "confidence_score": confidence,
        "difficulty": difficulty,
        "review_interval": interval_days,
        "last_reviewed_at": now,
        "next_review_at": next_review,
        "average_response_time": avg_rt,
        "recent_results": recent,
        "status": status,
        "last_reason_codes": reason_codes,
        "updated_at": now,
    }
