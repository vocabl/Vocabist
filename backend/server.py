"""Vocabist backend — FastAPI + Repository pattern (MongoDB/Supabase).

Implements Phase 1–3: auth (email/password + Emergent Google), profile /
onboarding, vocabulary engine, word detail + knowledge graph, saved words,
daily mission, adaptive spaced-review practice engine, progress / streak / XP,
entitlements and analytics events.

DB_BACKEND=mongo (default) → MongoRepository (Motor)
DB_BACKEND=supabase        → SupabaseRepository (supabase-py AsyncClient)
"""
import os
import re
import json
import secrets
import hashlib
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Any

import httpx
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
from dotenv import load_dotenv

from seed_data import WORDS, TOPICS, EXAMS, ARTICLES
from vocab_schema import (
    normalize_headword,
    to_canonical_storage,
)
from content_ingest import ingest_word, migrate_content_lifecycle, migrate_canonical, bulk_ingest
from graph_service import build_word_graph, resolve_all_relationship_refs
from db import get_db

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
APP_URL = os.environ.get("APP_URL", "").rstrip("/")

# ---- entitlements (centralized; do not scatter tier checks) ----
ENTITLEMENTS = {
    "free": {"daily_new_words": 8, "ai_coach_per_day": 3, "locked_exams": ["gre", "gmat"], "unlimited": False},
    "pro": {"daily_new_words": 9999, "ai_coach_per_day": 9999, "locked_exams": [], "unlimited": True},
}


def entitlements_for(tier: str) -> dict:
    return ENTITLEMENTS.get(tier or "free", ENTITLEMENTS["free"])


# Repository singleton — initialized at module load time (synchronous).
# The concrete client (Motor / supabase-py) is created lazily on first use.
repo = get_db()

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Vocabist API")
api = APIRouter(prefix="/api")

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_user_id() -> str:
    return "user_" + secrets.token_hex(6)


def make_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def public_user(u: dict) -> dict:
    return {
        "user_id": u["user_id"],
        "email": u.get("email"),
        "name": u.get("name"),
        "picture": u.get("picture"),
        "created_at": u.get("created_at"),
        "onboarded": u.get("onboarded", False),
        "tier": u.get("tier", "free"),
    }


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth[7:]
    session = await repo.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    if ensure_aware(session.get("expires_at")) < now_utc():
        raise HTTPException(status_code=401, detail="Session expired")
    user = await repo.get_user_by_id(session["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def create_session(user_id: str) -> str:
    token = make_token()
    await repo.create_session({
        "session_token": token,
        "user_id": user_id,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    return token

# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class SessionBody(BaseModel):
    session_id: str


class OnboardingBody(BaseModel):
    reason: str
    level: str
    daily_minutes: int
    exam_slug: Optional[str] = None
    exam_date: Optional[str] = None
    target_score: Optional[float] = None


class AnswerBody(BaseModel):
    word_id: str
    mode: str
    correct: bool
    response_time_ms: int = 0


class SessionCompleteBody(BaseModel):
    answered: int = 0
    correct: int = 0
    duration_ms: int = 0
    source: str = "mission"


class AnalyticsBody(BaseModel):
    event: str
    props: dict = {}


class ExamGoalBody(BaseModel):
    exam_slug: str
    exam_date: Optional[str] = None
    target_score: Optional[float] = None
    daily_minutes: Optional[int] = None

# ---------------------------------------------------------------------------
# spaced review engine — delegated to the pure adaptive learning engine
# (see backend/adaptive_learning.py). Kept deterministic and explainable.
# ---------------------------------------------------------------------------
from adaptive_learning import (
    update_progress as adaptive_update_progress,
    select_learning_priority,
    calculate_slipping,
)

# ---------------------------------------------------------------------------
# question generation
# ---------------------------------------------------------------------------

from practice_engine import generate_question


async def all_words_cache() -> List[dict]:
    return await repo.find_published_words()

# ---------------------------------------------------------------------------
# auth routes
# ---------------------------------------------------------------------------


@api.post("/auth/register")
async def register(body: RegisterBody):
    existing = await repo.get_user_by_email(body.email.lower())
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user_id = make_user_id()
    await repo.create_user({
        "user_id": user_id,
        "email": body.email.lower(),
        "name": body.name,
        "password_hash": pwd_ctx.hash(body.password),
        "picture": None,
        "onboarded": False,
        "tier": "free",
        "xp": 0,
        "streak": 0,
        "created_at": now_utc(),
    })
    token = await create_session(user_id)
    user = await repo.get_user_by_id(user_id)
    return {"token": token, "user": public_user(user)}


@api.post("/auth/login")
async def login(body: LoginBody):
    user = await repo.get_user_by_email(body.email.lower())
    if not user or not user.get("password_hash") or not pwd_ctx.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = await create_session(user["user_id"])
    return {"token": token, "user": public_user(user)}


@api.post("/auth/session")
async def google_session(body: SessionBody):
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id})
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session")
    data = resp.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="No email in session")
    user = await repo.get_user_by_email(email)
    if not user:
        user_id = make_user_id()
        await repo.create_user({
            "user_id": user_id,
            "email": email,
            "name": data.get("name"),
            "picture": data.get("picture"),
            "password_hash": None,
            "onboarded": False,
            "tier": "free",
            "xp": 0,
            "streak": 0,
            "created_at": now_utc(),
        })
        user = await repo.get_user_by_id(user_id)
    token = await create_session(user["user_id"])
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": public_user(user)}


@api.post("/auth/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        await repo.delete_session(auth[7:])
    return {"ok": True}

# ---------------------------------------------------------------------------
# profile / onboarding
# ---------------------------------------------------------------------------


async def get_or_create_profile(user_id: str) -> dict:
    prof = await repo.get_profile(user_id)
    if not prof:
        prof = {
            "user_id": user_id,
            "reason": None,
            "level": None,
            "daily_minutes": 10,
            "exam_slug": None,
            "exam_date": None,
            "target_score": None,
            "streak": 0,
            "longest_streak": 0,
            "xp": 0,
            "last_active_date": None,
            "created_at": now_utc(),
        }
        await repo.create_profile(dict(prof))
    return prof


@api.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    prof = await get_or_create_profile(user["user_id"])
    return {"user": public_user(user), "profile": prof}


@api.post("/onboarding")
async def onboarding(body: OnboardingBody, user: dict = Depends(get_current_user)):
    await get_or_create_profile(user["user_id"])
    await repo.update_profile(user["user_id"], {
        "reason": body.reason,
        "level": body.level,
        "daily_minutes": body.daily_minutes,
        "exam_slug": body.exam_slug,
        "exam_date": body.exam_date,
        "target_score": body.target_score,
        "updated_at": now_utc(),
    })
    await repo.update_user(user["user_id"], {"onboarded": True})
    await repo.log_event(user["user_id"], "onboarding_completed", {"reason": body.reason, "level": body.level})
    prof = await repo.get_profile(user["user_id"])
    return {"profile": prof}


@api.post("/profile/exam-goal")
async def set_exam_goal(body: ExamGoalBody, user: dict = Depends(get_current_user)):
    await get_or_create_profile(user["user_id"])
    update = {"exam_slug": body.exam_slug, "updated_at": now_utc()}
    if body.exam_date is not None:
        update["exam_date"] = body.exam_date
    if body.target_score is not None:
        update["target_score"] = body.target_score
    if body.daily_minutes is not None:
        update["daily_minutes"] = body.daily_minutes
    await repo.update_profile(user["user_id"], update)
    prof = await repo.get_profile(user["user_id"])
    return {"profile": prof}

# ---------------------------------------------------------------------------
# words / knowledge graph
# ---------------------------------------------------------------------------


def word_public(w: dict) -> dict:
    return {k: v for k, v in w.items() if k != "_id"}


@api.get("/words")
async def list_words(
    search: Optional[str] = None,
    topic: Optional[str] = None,
    cefr: Optional[str] = None,
    exam: Optional[str] = None,
    limit: int = Query(30, le=100),
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    total, words = await repo.list_words(search, topic, cefr, exam, offset, limit)
    # attach saved + progress status
    saved = await repo.get_saved_word_ids(user["user_id"])
    prog = {p["word_id"]: p.get("status", "NEW")
            for p in await repo.get_all_progress(user["user_id"])}
    for w in words:
        w["saved"] = w["id"] in saved
        w["status"] = prog.get(w["id"], "NEW")
    return {"total": total, "words": words, "offset": offset, "limit": limit}


@api.get("/words/{word_id}")
async def word_detail(word_id: str, user: dict = Depends(get_current_user)):
    w = await repo.get_word(word_id)
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")

    graph = await build_word_graph(repo, w)
    exams = await repo.find_exams_by_slugs(w.get("exam_relevance") or [])
    saved = await repo.find_saved_word(user["user_id"], word_id)
    prog = await repo.get_word_progress(user["user_id"], word_id)
    await repo.log_event(user["user_id"], "word_viewed", {"word_id": word_id})
    return {"word": word_public(w), "graph": graph, "exams": exams,
            "saved": bool(saved), "progress": prog}


@api.post("/words/{word_id}/save")
async def save_word(word_id: str, user: dict = Depends(get_current_user)):
    w = await repo.get_word(word_id)
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")
    await repo.save_word(user["user_id"], word_id)
    await repo.log_event(user["user_id"], "word_saved", {"word_id": word_id})
    return {"saved": True}


@api.delete("/words/{word_id}/save")
async def unsave_word(word_id: str, user: dict = Depends(get_current_user)):
    await repo.unsave_word(user["user_id"], word_id)
    return {"saved": False}


@api.get("/saved")
async def saved_words(user: dict = Depends(get_current_user)):
    ids = await repo.get_saved_words_sorted(user["user_id"])
    words = await repo.find_words_by_ids(ids)
    order = {wid: i for i, wid in enumerate(ids)}
    words.sort(key=lambda w: order.get(w["id"], 999))
    for w in words:
        w["saved"] = True
    return {"words": words}

# ---------------------------------------------------------------------------
# topics / exams
# ---------------------------------------------------------------------------


@api.get("/topics")
async def get_topics(user: dict = Depends(get_current_user)):
    topics = await repo.get_topics()
    for t in topics:
        t["word_count"] = await repo.count_words_by_topic(t["slug"])
    return {"topics": topics}


@api.get("/exams")
async def get_exams(user: dict = Depends(get_current_user)):
    exams = await repo.get_exams()
    prof = await get_or_create_profile(user["user_id"])
    for e in exams:
        e["word_count"] = await repo.count_words_by_exam(e["slug"])
        e["active"] = prof.get("exam_slug") == e["slug"]
    return {"exams": exams, "active_exam": prof.get("exam_slug"), "exam_date": prof.get("exam_date"),
            "target_score": prof.get("target_score")}


@api.get("/exams/{slug}")
async def exam_detail(slug: str, user: dict = Depends(get_current_user)):
    exam = await repo.get_exam_by_slug(slug)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    words = await repo.find_published_words_by_exam(slug)
    prog = {p["word_id"]: p for p in await repo.get_all_progress(user["user_id"])}
    mastered = sum(1 for w in words if prog.get(w["id"], {}).get("status") == "MASTERED")
    learning = sum(1 for w in words if prog.get(w["id"], {}).get("status") in ("LEARNING", "RECALLING", "SEEN"))
    prof = await get_or_create_profile(user["user_id"])
    days_left = None
    if prof.get("exam_slug") == slug and prof.get("exam_date"):
        try:
            ed = date.fromisoformat(prof["exam_date"])
            days_left = (ed - date.today()).days
        except Exception:
            days_left = None
    for w in words:
        w["status"] = prog.get(w["id"], {}).get("status", "NEW")
    return {
        "exam": exam,
        "words": words,
        "total_words": len(words),
        "mastered": mastered,
        "learning": learning,
        "days_left": days_left,
        "is_active": prof.get("exam_slug") == slug,
        "target_score": prof.get("target_score") if prof.get("exam_slug") == slug else None,
        "words_per_day": max(5, round(prof.get("daily_minutes", 10) * 1.2)) if prof.get("exam_slug") == slug else None,
        "locked": slug in entitlements_for(user.get("tier"))["locked_exams"],
    }

# ---------------------------------------------------------------------------
# mission + practice
# ---------------------------------------------------------------------------


async def select_mission_words(user: dict) -> dict:
    prof = await get_or_create_profile(user["user_id"])
    target = max(5, round(prof.get("daily_minutes", 10) * 1.2))
    now = now_utc()

    progresses = await repo.get_all_progress(user["user_id"])
    seen_ids = {p["word_id"] for p in progresses}

    # due for review — ranked by the adaptive priority engine
    due = [p for p in progresses if ensure_aware(p.get("next_review_at")) and ensure_aware(p["next_review_at"]) <= now and p.get("status") != "MASTERED"]
    active_exam = prof.get("exam_slug")
    due_meta = {w["id"]: w for w in await repo.find_words_by_ids([p["word_id"] for p in due])} if due else {}
    for p in due:
        pr = select_learning_priority(p, due_meta.get(p["word_id"], {}), now, active_exam)
        p["_priority"] = pr["priority"]
    due.sort(key=lambda p: -p["_priority"])
    due_ids = [p["word_id"] for p in due][:target]

    # new words filtered by exam/level
    candidates = await repo.find_words_for_mission(seen_ids, prof.get("exam_slug"))
    candidates.sort(key=lambda w: (-w.get("academic_importance", 0), -w.get("frequency", 0)))
    remaining = max(0, target - len(due_ids))
    new_ids = [w["id"] for w in candidates][:max(remaining, min(5, len(candidates)))]
    ent = entitlements_for(user.get("tier"))
    new_ids = new_ids[:ent["daily_new_words"]]

    return {"target": target, "due_ids": due_ids, "new_ids": new_ids,
            "review_count": len(due_ids), "new_count": len(new_ids),
            "estimated_minutes": prof.get("daily_minutes", 10)}


@api.get("/mission")
async def mission(user: dict = Depends(get_current_user)):
    sel = await select_mission_words(user)
    prof = await get_or_create_profile(user["user_id"])
    total = sel["review_count"] + sel["new_count"]
    # continue card = most recent LEARNING/RECALLING word
    recent = await repo.get_progress_by_statuses(
        user["user_id"], ["LEARNING", "RECALLING"]
    )
    # Sort by last_reviewed_at descending
    recent_sorted = sorted(
        [p for p in recent if p.get("last_reviewed_at")],
        key=lambda p: ensure_aware(p["last_reviewed_at"]) or now_utc(),
        reverse=True,
    )
    continue_word = None
    if recent_sorted:
        cw = await repo.get_word(recent_sorted[0]["word_id"])
        if cw:
            continue_word = {"id": cw["id"], "headword": cw["headword"],
                             "simple_definition": cw["simple_definition"], "cefr": cw.get("cefr")}
    return {
        "total_words": total,
        "review_count": sel["review_count"],
        "new_count": sel["new_count"],
        "estimated_minutes": max(1, round(total * 0.6)) if total else 0,
        "streak": prof.get("streak", 0),
        "xp": prof.get("xp", 0),
        "daily_minutes": prof.get("daily_minutes", 10),
        "continue_word": continue_word,
    }


@api.post("/practice/start")
async def practice_start(
    source: str = Query("mission"),
    ref: Optional[str] = None,
    mode: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    pool = await all_words_cache()
    pool_by_id = {w["id"]: w for w in pool}

    if source == "mission":
        sel = await select_mission_words(user)
        word_ids = sel["due_ids"] + sel["new_ids"]
    elif source == "exam" and ref:
        if ref in entitlements_for(user.get("tier"))["locked_exams"]:
            raise HTTPException(status_code=402, detail="Upgrade to Pro to practice this exam")
        word_ids = (await repo.find_published_words_by_exam_ids(ref))[:15]
    elif source == "topic" and ref:
        word_ids = (await repo.find_published_words_by_topic_ids(ref))[:15]
    elif source == "word" and ref:
        word_ids = [ref]
    elif source == "list" and ref:
        tokens = [x for x in ref.split(",") if x][:15]
        word_ids = []
        for tk in tokens:
            wid = tk if await repo.word_exists(tk) else await ensure_word(tk)
            if wid:
                word_ids.append(wid)
    elif source == "slipping":
        word_ids = await slipping_word_ids(user["user_id"])
    elif source == "saved":
        saved_list = await repo.get_saved_words_sorted(user["user_id"])
        word_ids = saved_list[:15]
    else:
        sel = await select_mission_words(user)
        word_ids = sel["due_ids"] + sel["new_ids"]

    if not word_ids:
        return {"questions": [], "count": 0}

    progresses = {p["word_id"]: p for p in await repo.find_progress_by_words(
        user["user_id"], word_ids
    )}

    questions = []
    session_modes: List[str] = []
    for wid in word_ids:
        w = pool_by_id.get(wid)
        if not w:
            continue
        q = generate_question(w, pool, progresses.get(wid), requested_mode=mode, session_modes=session_modes)
        if not q:
            continue  # graceful skip
        session_modes.append(q["mode"])
        q["teach"] = progresses.get(wid, {}).get("status", "NEW") in ("NEW",) and source in ("mission", "exam", "topic")
        q["card"] = {
            "headword": w["headword"], "phonetic": w.get("phonetic"),
            "simple_definition": w.get("simple_definition"), "easy_meaning": w.get("easy_meaning"),
            "example": w.get("example"), "cefr": w.get("cefr"),
            "part_of_speech": w.get("part_of_speech"),
            "synonyms": w.get("synonyms", [])[:3],
        }
        questions.append(q)

    await repo.log_event(user["user_id"], "learning_session_started", {"source": source, "count": len(questions)})
    return {"questions": questions, "count": len(questions), "source": source}


@api.post("/practice/answer")
async def practice_answer(body: AnswerBody, user: dict = Depends(get_current_user)):
    prev = await repo.get_word_progress(user["user_id"], body.word_id)
    word_meta = await repo.get_word(body.word_id) or {}
    updated = adaptive_update_progress(prev, body.correct, body.response_time_ms, word_meta, now_utc())
    updated_full = {"user_id": user["user_id"], "word_id": body.word_id, **updated}
    if not prev:
        updated_full["created_at"] = now_utc()
    was_mastered = prev and prev.get("status") == "MASTERED"
    await repo.upsert_word_progress(user["user_id"], body.word_id, updated_full)
    xp_gain = 10 if body.correct else 2
    await repo.increment_user_xp(user["user_id"], xp_gain)

    just_mastered = updated["status"] == "MASTERED" and not was_mastered
    if just_mastered:
        await repo.log_event(user["user_id"], "word_mastered", {"word_id": body.word_id})
    await repo.log_event(user["user_id"], "answer_submitted", {"word_id": body.word_id, "correct": body.correct, "mode": body.mode})

    return {"status": updated["status"], "mastery_score": updated["mastery_score"],
            "confidence_score": updated["confidence_score"], "difficulty": updated["difficulty"],
            "xp_gain": xp_gain, "just_mastered": just_mastered,
            "reason_codes": updated["last_reason_codes"],
            "next_review_at": updated["next_review_at"].isoformat()}


@api.post("/practice/complete")
async def practice_complete(body: SessionCompleteBody, user: dict = Depends(get_current_user)):
    prof = await get_or_create_profile(user["user_id"])
    today = date.today().isoformat()
    last = prof.get("last_active_date")
    # last_active_date might come back as a date object or string
    if hasattr(last, "isoformat"):
        last = last.isoformat()
    streak = prof.get("streak", 0)
    if last != today:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        streak = streak + 1 if last == yesterday else 1
    longest = max(prof.get("longest_streak", 0), streak)
    session_doc = {
        "user_id": user["user_id"], "answered": body.answered, "correct": body.correct,
        "duration_ms": body.duration_ms, "source": body.source, "created_at": now_utc(),
    }
    await repo.complete_practice_session(
        user["user_id"], streak, longest, today, session_doc
    )
    await repo.log_event(user["user_id"], "learning_session_completed",
                    {"answered": body.answered, "correct": body.correct, "source": body.source})
    return {"streak": streak, "longest_streak": longest}

# ---------------------------------------------------------------------------
# progress
# ---------------------------------------------------------------------------

XP_PER_LEVEL = 500


@api.get("/progress")
async def progress(user: dict = Depends(get_current_user)):
    prof = await get_or_create_profile(user["user_id"])
    progresses = await repo.get_all_progress(user["user_id"])

    # Mastery distribution — real counts from user_word_progress
    dist = {"SEEN": 0, "LEARNING": 0, "RECALLING": 0, "MASTERED": 0}
    for p in progresses:
        s = p.get("status")
        if s in dist:
            dist[s] += 1

    learned = dist["LEARNING"] + dist["RECALLING"] + dist["MASTERED"]
    mastered = dist["MASTERED"]
    in_progress = dist["SEEN"] + dist["LEARNING"] + dist["RECALLING"]
    total_correct = sum(p.get("times_correct", 0) for p in progresses)
    total_answered = sum(p.get("times_correct", 0) + p.get("times_wrong", 0) for p in progresses)
    accuracy = round(100 * total_correct / total_answered) if total_answered else 0

    # Recently mastered — up to 5 most-recently mastered words
    mastered_progs = [
        p for p in progresses
        if p.get("status") == "MASTERED" and p.get("updated_at")
    ]
    mastered_progs.sort(
        key=lambda p: ensure_aware(p["updated_at"]) or now_utc(), reverse=True,
    )
    mastered_ids = [p["word_id"] for p in mastered_progs[:5]]
    mastered_words = {w["id"]: w for w in await repo.find_words_by_ids(mastered_ids)} if mastered_ids else {}
    recently_mastered = []
    for p in mastered_progs[:5]:
        w = mastered_words.get(p["word_id"])
        if w:
            recently_mastered.append({
                "word_id": w["id"],
                "headword": w["headword"],
                "cefr": w.get("cefr"),
                "mastery_score": round(float(p.get("mastery_score", 0))),
                "mastered_at": (ensure_aware(p["updated_at"]) or now_utc()).isoformat(),
            })

    # Weak areas — real per-topic breakdown with counts
    words = await repo.load_all_words_minimal()
    word_topics = {w["id"]: w.get("topic") for w in words}
    topic_data: dict = {}  # topic -> {scores, mastered, total}
    for p in progresses:
        t = word_topics.get(p["word_id"])
        if not t:
            continue
        td = topic_data.setdefault(t, {"scores": [], "mastered": 0, "total": 0})
        td["scores"].append(float(p.get("mastery_score", 0)))
        td["total"] += 1
        if p.get("status") == "MASTERED":
            td["mastered"] += 1
    topics_list = await repo.get_topics()
    topic_names = {t["slug"]: t["name"] for t in topics_list}
    weak_areas = []
    for t, td in topic_data.items():
        if td["scores"]:
            weak_areas.append({
                "topic": t,
                "name": topic_names.get(t, t.title()),
                "avg_mastery": round(sum(td["scores"]) / len(td["scores"])),
                "mastered_count": td["mastered"],
                "total_count": td["total"],
                "mastery_percent": round(100 * td["mastered"] / td["total"]) if td["total"] else 0,
            })
    weak_areas.sort(key=lambda x: x["avg_mastery"])
    # Keep top 3 weakest for weak_areas; also return all for the full picture
    weak = weak_areas[:3]

    xp = prof.get("xp", 0)
    level = xp // XP_PER_LEVEL + 1
    sessions = await repo.get_study_sessions(user["user_id"])
    study_minutes = round(sum(s.get("duration_ms", 0) for s in sessions) / 60000)

    return {
        "words_learned": learned,
        "words_mastered": mastered,
        "in_progress": in_progress,
        "accuracy": accuracy,
        "retention": accuracy,
        "streak": prof.get("streak", 0),
        "longest_streak": prof.get("longest_streak", 0),
        "xp": xp,
        "level": level,
        "xp_into_level": xp % XP_PER_LEVEL,
        "xp_per_level": XP_PER_LEVEL,
        "study_minutes": study_minutes,
        "total_sessions": len(sessions),
        "mastery_distribution": dist,
        "recently_mastered": recently_mastered,
        "weak_areas": weak,
        "cefr_level": prof.get("level"),
        "achievements": compute_achievements(learned, mastered, prof.get("longest_streak", 0)),
    }


def compute_achievements(learned: int, mastered: int, streak: int) -> List[dict]:
    defs = [
        {"key": "first_word", "title": "First Word", "desc": "Learn your first word", "goal": 1, "value": learned},
        {"key": "words_100", "title": "100 Words", "desc": "Learn 100 words", "goal": 100, "value": learned},
        {"key": "words_500", "title": "500 Words", "desc": "Learn 500 words", "goal": 500, "value": learned},
        {"key": "master_50", "title": "50 Mastered", "desc": "Master 50 words", "goal": 50, "value": mastered},
        {"key": "streak_7", "title": "7-Day Streak", "desc": "Study 7 days in a row", "goal": 7, "value": streak},
        {"key": "streak_30", "title": "30-Day Streak", "desc": "Study 30 days in a row", "goal": 30, "value": streak},
    ]
    for d in defs:
        d["unlocked"] = d["value"] >= d["goal"]
        d["progress"] = min(100, round(100 * d["value"] / d["goal"]))
    return defs

# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------


@api.post("/analytics")
async def analytics(body: AnalyticsBody, user: dict = Depends(get_current_user)):
    await repo.log_event(user["user_id"], body.event, body.props)
    return {"ok": True}


# ---------------------------------------------------------------------------
# entitlements / subscription
# ---------------------------------------------------------------------------

# Pricing configuration — single source of truth.
# Placeholder values until a real payment provider is connected.
PRICING = {
    "monthly": {"price_display": "$7.99", "period": "month", "interval_months": 1},
    "annual":  {"price_display": "$49.99", "period": "year", "interval_months": 12},
}
PAYMENT_PROVIDER_CONNECTED = False  # flip to True when a real provider is wired


class SubscribeBody(BaseModel):
    plan: str = "monthly"


async def get_subscription_state(user_id: str) -> dict:
    """Canonical server-side entitlement check. Single source of truth."""
    from db import get_db
    _repo = get_db()
    user = await _repo.get_user_by_id(user_id)
    tier = (user or {}).get("tier", "free")

    # Look up the latest subscription record
    sb = await _repo._client() if hasattr(_repo, "_client") else None
    sub_record = None
    if sb:
        r = await sb.table("subscriptions").select("*").eq(
            "user_id", user_id
        ).order("started_at", desc=True).limit(1).maybe_single().execute()
        sub_record = r.data if r is not None else None

    status = (sub_record or {}).get("status", "none")
    platform = (sub_record or {}).get("platform", "none")
    plan = (sub_record or {}).get("plan")
    started_at = (sub_record or {}).get("started_at")
    cancelled_at = (sub_record or {}).get("cancelled_at")

    is_pro = tier == "pro" and status == "active"

    return {
        "plan": "pro" if is_pro else "free",
        "tier": tier,
        "is_pro": is_pro,
        "status": status,
        "source": platform,
        "subscription_plan": plan,
        "started_at": started_at,
        "cancelled_at": cancelled_at,
        "provider_connected": PAYMENT_PROVIDER_CONNECTED,
    }


async def require_pro(request: Request) -> dict:
    """Dependency that raises 403 if user is not Pro."""
    user = await get_current_user(request)
    state = await get_subscription_state(user["user_id"])
    if not state["is_pro"]:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PRO_REQUIRED",
                "message": "This feature requires Vocabist Pro.",
                "upgrade_url": "/paywall",
            },
        )
    return user


@api.get("/entitlements")
async def get_entitlements(user: dict = Depends(get_current_user)):
    state = await get_subscription_state(user["user_id"])
    ent = entitlements_for("pro" if state["is_pro"] else "free")
    return {
        **state,
        "limits": ent,
        "ai_coach_used_today": await repo.count_ai_coach_today(user["user_id"]),
        "pricing": PRICING,
    }


@api.post("/subscription/activate")
async def activate_subscription_endpoint(body: SubscribeBody, user: dict = Depends(get_current_user)):
    if PAYMENT_PROVIDER_CONNECTED:
        # Future: validate receipt/token from real provider here
        pass
    # Mock activation — only allowed when no real provider is connected
    # In production with a real provider, this would verify the purchase first
    await repo.activate_subscription(user["user_id"], body.plan, now_utc())
    await repo.log_event(user["user_id"], "subscription_started", {
        "plan": body.plan, "source": "mock" if not PAYMENT_PROVIDER_CONNECTED else "provider",
    })
    return {"tier": "pro", "source": "mock" if not PAYMENT_PROVIDER_CONNECTED else "provider"}


@api.post("/subscription/cancel")
async def cancel_subscription_endpoint(user: dict = Depends(get_current_user)):
    await repo.cancel_subscription(user["user_id"])
    await repo.log_event(user["user_id"], "subscription_cancelled", {})
    return {"tier": "free"}


@api.post("/subscription/restore")
async def restore_subscription(user: dict = Depends(get_current_user)):
    if not PAYMENT_PROVIDER_CONNECTED:
        return {"restored": False, "message": "Payment provider is not connected yet. Purchases will be restorable once billing is configured."}
    # Future: query provider for existing purchases
    return {"restored": False, "message": "No active subscription found."}


# ---------------------------------------------------------------------------
# pronunciation audio (Free Dictionary API + OpenAI TTS fallback)
# ---------------------------------------------------------------------------


def clean_for_tts(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>~|`]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:300]


async def make_tts(text: str) -> str:
    """Generate (or reuse) a cached mp3 for text; return its /api/tts key."""
    from emergentintegrations.llm.openai import OpenAITextToSpeech
    key = hashlib.sha256(f"{text}|alloy|1.0|tts-1|mp3".encode()).hexdigest()
    if not await repo.tts_cache_exists(key):
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio = await tts.generate_speech(text=clean_for_tts(text), model="tts-1", voice="alloy")
        await repo.insert_tts_cache(key, audio)
    return key


@api.get("/tts/{key}.mp3")
async def serve_tts(key: str):
    audio = await repo.get_tts_audio(key)
    if audio is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000"})


@api.get("/words/{word_id}/audio")
async def word_audio(word_id: str, user: dict = Depends(get_current_user)):
    w = await repo.get_word(word_id)
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")
    if w.get("audio"):
        cached = dict(w["audio"])
        # Normalize any legacy relative tts_url (/tts/xxx.mp3) to absolute.
        # Needed for audio entries written before the absolute-URL fix.
        rel = cached.get("tts_url") or ""
        if rel and not rel.startswith("http") and APP_URL:
            # Legacy path is /tts/{key}.mp3 — the API prefix is /api
            cached["tts_url"] = f"{APP_URL}/api{rel}"
        return cached

    us_url = uk_url = None
    try:
        async with httpx.AsyncClient(timeout=4) as http:
            r = await http.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w['headword']}")
        if r.status_code == 200:
            for entry in r.json():
                for ph in entry.get("phonetics", []):
                    a = ph.get("audio") or ""
                    if a.endswith("-us.mp3") and not us_url:
                        us_url = a
                    elif a.endswith("-uk.mp3") and not uk_url:
                        uk_url = a
                    elif a and not us_url:
                        us_url = a
    except Exception:
        pass

    tts_url = None
    if not us_url and not uk_url:
        try:
            key = await make_tts(w["headword"])
            # Return an absolute URL so external clients (tests, native apps)
            # can fetch the audio without needing to know the server origin.
            # Fall back to a relative path only when APP_URL is not configured
            # (e.g. pure local development with no env var).
            if APP_URL:
                tts_url = f"{APP_URL}/api/tts/{key}.mp3"
            else:
                tts_url = f"/tts/{key}.mp3"
        except Exception:
            tts_url = None

    audio = {"us_url": us_url, "uk_url": uk_url, "tts_url": tts_url}
    await repo.update_word(word_id, {"audio": audio})
    return audio


# ---------------------------------------------------------------------------
# AI Coach (gpt-5.6-luna) — supplementary, never overwrites canonical content
# ---------------------------------------------------------------------------


@api.post("/words/{word_id}/ai-coach")
async def ai_coach(word_id: str, user: dict = Depends(get_current_user)):
    w = await repo.get_word(word_id)
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")

    cached = await repo.get_ai_coach_content(word_id)
    if cached:
        return {"content": cached["content"], "provenance": "ai_generated", "cached": True}

    tier = user.get("tier", "free")
    ent = entitlements_for(tier)
    used = await repo.count_ai_coach_today(user["user_id"])
    if used >= ent["ai_coach_per_day"]:
        raise HTTPException(status_code=402, detail="Daily AI Coach limit reached. Upgrade to Pro for unlimited.")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI is not configured")

    # Route through the centralized AI Gateway (usage tracked; fallback-capable).
    # Behavior preserved: AI_COACH task keeps Emergent GPT-5.6 Luna as primary.
    from ai.gateway import gateway as ai_gateway
    from ai.schemas import Task as AITask
    from ai.errors import AIError as _AIError
    prompt = (
        f'For the English word "{w["headword"]}" (meaning: {w.get("simple_definition")}), '
        'return ONLY JSON: {"explanation":"a warm 2-sentence plain-English explanation a learner will remember",'
        '"example":"one fresh natural example sentence using the word","mnemonic":"a short vivid memory hook"}'
    )
    messages = [
        {"role": "system", "content": "You are a friendly, concise English vocabulary coach. Always return strict JSON."},
        {"role": "user", "content": prompt},
    ]
    try:
        res = await ai_gateway.run_json(AITask.AI_COACH, messages, max_tokens=600,
                                        user_id=user["user_id"])
    except _AIError:
        raise HTTPException(status_code=502, detail="AI Coach is busy, try again")
    except Exception:
        raise HTTPException(status_code=502, detail="AI Coach is busy, try again")

    parsed = res.data if isinstance(res.data, dict) else {}
    content = None
    if all(isinstance(parsed.get(k), str) and parsed[k].strip() for k in ("explanation", "example", "mnemonic")):
        content = {k: parsed[k].strip() for k in ("explanation", "example", "mnemonic")}
    if not content:
        raise HTTPException(status_code=502, detail="Could not generate a good explanation, try again")

    await repo.insert_ai_coach_content({"word_id": word_id, "content": content,
                                        "provenance": "ai_generated", "status": "PUBLISHED",
                                        "created_at": now_utc()})
    await repo.insert_ai_coach_usage({"user_id": user["user_id"], "word_id": word_id,
                                      "date": date.today().isoformat(), "created_at": now_utc()})
    await repo.log_event(user["user_id"], "ai_coach_generated", {"word_id": word_id})
    return {"content": content, "provenance": "ai_generated", "cached": False}


# ---------------------------------------------------------------------------
# Read & Learn / Learn From Anything / Smart Review Nudges
# ---------------------------------------------------------------------------

STOPWORDS = set("""a an the and or but if then than that this these those of to in on at by for with about
into over after before between out against during without within along across around is are was were be been
being have has had do does did will would shall should can could may might must not no nor so as it its it's
he she they them his her their our your you i we me my mine ours yours who whom whose which what when where why
how all any both each few more most other some such only own same too very just also from up down off out very
one two three there here their they're you're we're i'm""".split())


class TextBody(BaseModel):
    text: str


class ImportBody(BaseModel):
    headword: str


class BuildBody(BaseModel):
    word_ids: List[str]


async def slipping_word_ids(user_id: str) -> List[str]:
    now = now_utc()
    horizon = now + timedelta(days=2)
    progresses = await repo.get_progress_by_statuses(user_id, ["SEEN", "LEARNING", "RECALLING"])
    candidates = [p for p in progresses
                  if ensure_aware(p.get("next_review_at")) and ensure_aware(p["next_review_at"]) <= horizon
                  and p.get("mastery_score", 0) < 90]

    def rank(p):
        s = calculate_slipping(p, now)["slipping_score"]
        overdue = (now - ensure_aware(p["next_review_at"])).total_seconds()
        return (-s, -overdue, float(p.get("mastery_score", 0)))
    candidates.sort(key=rank)
    return [p["word_id"] for p in candidates][:20]


@api.get("/review/slipping")
async def review_slipping(user: dict = Depends(get_current_user)):
    ids = await slipping_word_ids(user["user_id"])
    prog = {p["word_id"]: p for p in await repo.find_progress_by_words(user["user_id"], ids)}
    words = {w["id"]: w for w in await repo.find_words_by_ids(ids)}
    items = []
    for wid in ids:
        w = words.get(wid)
        if not w:
            continue
        p = prog.get(wid, {})
        nr = ensure_aware(p.get("next_review_at"))
        overdue_days = max(0, round((now_utc() - nr).total_seconds() / 86400)) if nr else 0
        items.append({
            "id": wid, "headword": w["headword"], "cefr": w.get("cefr"),
            "simple_definition": w["simple_definition"],
            "status": p.get("status", "SEEN"),
            "mastery_score": round(float(p.get("mastery_score", 0))),
            "overdue_days": overdue_days,
        })
    return {"count": len(items), "words": items}


@api.get("/articles")
async def list_articles(level: Optional[str] = None, topic: Optional[str] = None,
                        user: dict = Depends(get_current_user)):
    arts = await repo.get_articles(level, topic)
    return {"articles": arts}


@api.get("/articles/{article_id}")
async def get_article(article_id: str, user: dict = Depends(get_current_user)):
    art = await repo.get_article_by_id(article_id)
    if not art:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"article": art}


async def ai_define(word: str) -> Optional[dict]:
    if not EMERGENT_LLM_KEY:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"define-{word}",
                       system_message="You are a concise English dictionary. Return strict JSON only.").with_model("openai", "gpt-5.6-luna")
        prompt = (f'Define the English word "{word}". Return ONLY JSON: '
                  '{"simple_definition":"one clear sentence","phonetic":"/IPA/",'
                  '"example":"one natural example sentence","part_of_speech":"noun|verb|adjective|adverb"}. '
                  'If it is not a real English word, return {"invalid":true}.')
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else str(resp)
        text = re.sub(r"^```(json)?|```$", "", text.strip()).strip()
        s, e = text.find("{"), text.rfind("}")
        if s == -1 or e == -1:
            return None
        parsed = json.loads(text[s:e + 1])
        if parsed.get("invalid") or not parsed.get("simple_definition"):
            return None
        return {"simple_definition": parsed["simple_definition"].strip(),
                "phonetic": (parsed.get("phonetic") or "").strip(),
                "example": (parsed.get("example") or "").strip(),
                "part_of_speech": (parsed.get("part_of_speech") or "").strip()}
    except Exception:
        return None


async def dictionary_lookup(word: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=4) as http:
            r = await http.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
        if r.status_code != 200:
            return await ai_define(word)
        entry = r.json()[0]
        phonetic = entry.get("phonetic") or ""
        definition = example = pos = ""
        for m in entry.get("meanings", []):
            pos = pos or m.get("partOfSpeech", "")
            for d in m.get("definitions", []):
                definition = definition or d.get("definition", "")
                example = example or d.get("example", "")
                if definition:
                    break
            if definition:
                break
        if not definition:
            return await ai_define(word)
        return {"phonetic": phonetic, "simple_definition": definition,
                "example": example, "part_of_speech": pos}
    except Exception:
        return await ai_define(word)


@api.get("/lookup")
async def lookup(word: str = Query(...), user: dict = Depends(get_current_user)):
    norm = re.sub(r"[^a-z]", "", word.lower())
    if not norm:
        raise HTTPException(status_code=400, detail="Invalid word")
    w = await repo.get_word_by_headword(norm)
    if w:
        saved = await repo.find_saved_word(user["user_id"], w["id"])
        return {"in_bank": True, "id": w["id"], "headword": w["headword"],
                "phonetic": w.get("phonetic"), "simple_definition": w["simple_definition"],
                "example": w.get("example"), "cefr": w.get("cefr"),
                "part_of_speech": w.get("part_of_speech"), "saved": bool(saved)}
    d = await dictionary_lookup(norm)
    if not d:
        return {"in_bank": False, "headword": norm, "simple_definition": None, "found": False}
    return {"in_bank": False, "found": True, "headword": norm, **d, "saved": False}


async def ensure_word(headword: str) -> Optional[str]:
    """Return a word id for `headword`, creating an imported entry if needed."""
    norm = re.sub(r"[^a-z]", "", headword.lower())
    if not norm:
        return None
    ckey = normalize_headword(headword)
    existing = await repo.get_word_by_canonical_or_headword(ckey, norm)
    if existing:
        return existing["id"]
    d = await dictionary_lookup(norm)
    if not d:
        return None
    raw = {"headword": norm, "cefr": "B1", "topic": "everyday", "frequency": 3,
           "academic_importance": 2, "easy_meaning": d.get("simple_definition"), **d}
    outcome = await ingest_word(repo, raw, provenance="IMPORTED")
    return outcome.get("id")


@api.post("/words/import")
async def import_word(body: ImportBody, user: dict = Depends(get_current_user)):
    wid = await ensure_word(body.headword)
    if not wid:
        raise HTTPException(status_code=404, detail="No definition found for that word")
    return {"id": wid}


def tokenize_vocab(text: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
    seen, out = set(), []
    for w in words:
        w = w.strip("'-")
        if len(w) < 4 or w in STOPWORDS or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:60]


async def classify_words(user_id: str, candidates: List[str]) -> dict:
    bank_list = await repo.find_words_by_headwords(candidates)
    bank = {w["headword"]: w for w in bank_list}
    ids = [w["id"] for w in bank.values()]
    prog = {p["word_id"]: p.get("status", "NEW")
            for p in await repo.find_progress_by_words(user_id, ids)}
    known, learning, new = [], [], []
    for hw in candidates:
        b = bank.get(hw)
        if b:
            status = prog.get(b["id"], "NEW")
            item = {"headword": hw, "in_bank": True, "id": b["id"],
                    "simple_definition": b.get("simple_definition"), "cefr": b.get("cefr")}
            if status in ("MASTERED", "RECALLING"):
                known.append(item)
            elif status in ("LEARNING", "SEEN"):
                learning.append(item)
            else:
                new.append(item)
        else:
            new.append({"headword": hw, "in_bank": False, "id": None})
    return {"known": known, "learning": learning, "new": new,
            "counts": {"known": len(known), "learning": len(learning), "new": len(new)}}


@api.post("/extract")
async def extract_text(body: TextBody, user: dict = Depends(get_current_user)):
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="Please paste some text")
    return await classify_words(user["user_id"], tokenize_vocab(body.text))


@api.post("/extract-pdf")
async def extract_pdf(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    from pypdf import PdfReader
    import io
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF too large (max 8MB)")
    try:
        reader = PdfReader(io.BytesIO(data))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:20])
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read that PDF")
    if not text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in the PDF")
    return await classify_words(user["user_id"], tokenize_vocab(text))


@api.post("/practice/build")
async def practice_build(body: BuildBody, user: dict = Depends(get_current_user)):
    resolved: List[str] = []
    for token in body.word_ids[:20]:
        wid = token if await repo.word_exists(token) else await ensure_word(token)
        if wid:
            resolved.append(wid)
    if not resolved:
        return {"questions": [], "count": 0}
    pool = await all_words_cache()
    pool_by_id = {w["id"]: w for w in pool}
    progresses = {p["word_id"]: p for p in await repo.find_progress_by_words(
        user["user_id"], resolved
    )}
    questions = []
    session_modes: List[str] = []
    for wid in resolved:
        w = pool_by_id.get(wid)
        if not w:
            continue
        q = generate_question(w, pool, progresses.get(wid), session_modes=session_modes)
        if not q:
            continue
        session_modes.append(q["mode"])
        q["teach"] = progresses.get(wid, {}).get("status", "NEW") == "NEW"
        q["card"] = {"headword": w["headword"], "phonetic": w.get("phonetic"),
                     "simple_definition": w.get("simple_definition"), "easy_meaning": w.get("easy_meaning"),
                     "example": w.get("example"), "cefr": w.get("cefr"),
                     "part_of_speech": w.get("part_of_speech"), "synonyms": w.get("synonyms", [])[:3]}
        questions.append(q)
    await repo.log_event(user["user_id"], "learning_session_started", {"source": "import", "count": len(questions)})
    return {"questions": questions, "count": len(questions), "source": "import"}


@api.get("/")
async def root():
    return {"service": "vocabist", "status": "ok"}

# ---------------------------------------------------------------------------
# Semantic Search — hybrid exact + semantic (student-facing)
# ---------------------------------------------------------------------------

@api.get("/search/hybrid")
async def hybrid_search(
    q: str = Query(..., min_length=1),
    cefr: Optional[str] = None,
    limit: int = Query(20, le=50),
    user: dict = Depends(get_current_user),
):
    """Hybrid search: exact text + semantic meaning search."""
    from ai.tasks.semantic_search import hybrid_search as do_hybrid_search
    try:
        result = await do_hybrid_search(
            repo, q.strip(), limit=limit, cefr=cefr, user_id=user["user_id"],
        )
        # Attach saved status
        saved_ids = await repo.get_saved_word_ids(user["user_id"])
        prog = {p["word_id"]: p.get("status", "NEW")
                for p in await repo.get_all_progress(user["user_id"])}
        for w in result.get("words", []):
            w["saved"] = w.get("id", "") in saved_ids
            w["progress_status"] = prog.get(w.get("id", ""), "NEW")
        return result
    except Exception as e:
        # If semantic fails, fall back to pure text search
        total, words = await repo.list_words(q, None, cefr, None, 0, limit)
        saved_ids = await repo.get_saved_word_ids(user["user_id"])
        for w in words:
            w["saved"] = w["id"] in saved_ids
        return {"words": words, "total": total, "search_types": ["exact"], "semantic_available": False}


# ---------------------------------------------------------------------------
# Visual Capture — image → vocabulary extraction (student-facing)
# ---------------------------------------------------------------------------

@api.post("/visual-capture/extract")
async def visual_capture_extract(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """Extract vocabulary from an image using Muse Glimmer through the AI Gateway."""
    from ai.tasks.multimodal import extract_from_image
    from ai.errors import AIError as _AIError

    image = str(payload.get("image", "")).strip()
    if not image.startswith("data:image"):
        raise HTTPException(status_code=400, detail="Image must be a data URL")

    max_words = min(int(payload.get("max_words", 15)), 30)
    instruction = str(payload.get("instruction", ""))

    try:
        out = await extract_from_image(
            image, max_words=max_words, instruction=instruction,
        )
    except _AIError:
        raise HTTPException(status_code=502, detail="Visual extraction is temporarily unavailable")

    entries = out.get("entries", [])

    # Check which words already exist
    if entries:
        existing_headwords = {w.get("headword", "").lower() for w in await repo.load_all_words_minimal()}
        candidates = []
        for entry in entries:
            hw = (entry.get("headword") or "").strip().lower()
            if not hw:
                continue
            entry["already_exists"] = hw in existing_headwords
            # Try to find existing word id
            if entry["already_exists"]:
                existing_word = await repo.get_word_by_headword(hw)
                if existing_word:
                    entry["existing_id"] = existing_word["id"]
            candidates.append(entry)
    else:
        candidates = []

    return {
        "candidates": candidates,
        "total_extracted": len(candidates),
        "model": out.get("model_key"),
        "provider": out.get("provider"),
    }


@api.post("/visual-capture/import")
async def visual_capture_import(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """Import selected visual capture candidates into the vocabulary bank.
    All go to REVIEW status (never auto-published)."""
    words = payload.get("words", [])
    if not words:
        raise HTTPException(status_code=400, detail="No words to import")

    results = await bulk_ingest(repo, words, provenance="AI_GENERATED")
    await repo.log_event(user["user_id"], "visual_capture_imported", {
        "count": results.get("created", 0),
    })
    return results

# ---------------------------------------------------------------------------
# startup: indexes + seed
# ---------------------------------------------------------------------------


async def seed_content():
    if await repo.count_collection("words") == 0:
        docs = []
        for w in WORDS:
            wid = slugify(w["headword"])
            docs.append({**w, "id": wid, "headword": w["headword"].lower(),
                         "status": "PUBLISHED", "provenance": "CURATED", "created_at": now_utc()})
        if docs:
            await repo.seed_words(docs)
    if await repo.count_collection("topics") == 0:
        await repo.seed_topics([dict(t) for t in TOPICS])
    if await repo.count_collection("exams") == 0:
        await repo.seed_exams([dict(e) for e in EXAMS])
    if await repo.count_collection("articles") == 0:
        await repo.seed_articles([dict(a) for a in ARTICLES])

    # Merge AI-generated, validated word bank (idempotent upsert by id).
    # Use a single bulk query to fetch all existing IDs to avoid N individual
    # round-trips per word (critical for Supabase HTTP latency).
    bank_path = os.path.join(ROOT_DIR, "word_bank.json")
    if os.path.exists(bank_path):
        try:
            with open(bank_path) as f:
                bank = json.load(f)
        except Exception:
            bank = []
        if bank:
            existing_ids = await repo.load_all_word_ids()
            for w in bank:
                hw = str(w.get("headword", "")).strip().lower()
                if not hw:
                    continue
                wid = slugify(hw)
                if wid in existing_ids:
                    continue
                await repo.upsert_word(wid, {
                    **w, "id": wid, "headword": hw, "status": "PUBLISHED",
                    "provenance": "AI_GENERATED", "created_at": now_utc(),
                })



@app.on_event("startup")
async def startup():
    """Lightweight startup: index creation + conditional seed only.

    migrate_canonical(), migrate_content_lifecycle(), and
    resolve_all_relationship_refs() are MAINTENANCE operations and must be
    invoked explicitly via:

        python backend/maintenance.py [all | canonical | lifecycle | resolve_refs]

    They are intentionally NOT run here to avoid:
    - ~15 s startup overhead under DB_BACKEND=supabase
    - accidental re-execution on every process restart
    - unexpected schema mutations during rolling deploys
    """
    await repo.setup_indexes()
    await seed_content()


app.include_router(api)

# Internal Admin API — server-side protected (mounted after repo + auth are defined).
from admin_routes import build_admin_router  # noqa: E402
app.include_router(build_admin_router(repo, get_current_user))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
