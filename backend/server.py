"""Vocabist backend — FastAPI + MongoDB (Motor).

Implements Phase 1–3: auth (email/password + Emergent Google), profile /
onboarding, vocabulary engine, word detail + knowledge graph, saved words,
daily mission, adaptive spaced-review practice engine, progress / streak / XP,
entitlements and analytics events.
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
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from dotenv import load_dotenv

from seed_data import WORDS, TOPICS, EXAMS, ARTICLES
from vocab_schema import (
    normalize_headword,
    to_canonical_storage,
)
from content_ingest import ingest_word, migrate_content_lifecycle
from graph_service import build_word_graph, resolve_all_relationship_refs

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "vocably")
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

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
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
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    if ensure_aware(session.get("expires_at")) < now_utc():
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def create_session(user_id: str) -> str:
    token = make_token()
    await db.user_sessions.insert_one({
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

MODES = ["multiple_choice", "synonym_select", "true_false", "spelling", "fill_blank"]


async def all_words_cache() -> List[dict]:
    return await db.words.find({"status": "PUBLISHED"}, {"_id": 0}).to_list(1000)


def build_question(word: dict, mode: str, pool: List[dict]) -> dict:
    others = [w for w in pool if w["id"] != word["id"]]
    import random
    rnd = random.Random(word["id"] + mode)

    base = {"word_id": word["id"], "headword": word["headword"], "mode": mode,
            "phonetic": word.get("phonetic"), "part_of_speech": word.get("part_of_speech")}

    if mode == "multiple_choice":
        distractors = rnd.sample(others, min(3, len(others)))
        options = [word["simple_definition"]] + [d["simple_definition"] for d in distractors]
        rnd.shuffle(options)
        return {**base, "prompt": f"What does “{word['headword']}” mean?",
                "options": options, "answer": word["simple_definition"]}

    if mode == "synonym_select" and word.get("synonyms"):
        correct = word["synonyms"][0]
        distractors = rnd.sample(others, min(3, len(others)))
        options = [correct] + [d["headword"] for d in distractors]
        rnd.shuffle(options)
        return {**base, "prompt": f"Which word is a synonym of “{word['headword']}”?",
                "options": options, "answer": correct}

    if mode == "true_false":
        show_true = rnd.random() > 0.5
        if show_true or not others:
            shown_def = word["simple_definition"]
            answer = "True"
        else:
            shown_def = rnd.choice(others)["simple_definition"]
            answer = "False"
        return {**base, "prompt": f"“{word['headword']}” means: {shown_def}",
                "options": ["True", "False"], "answer": answer}

    if mode == "spelling":
        return {**base, "prompt": f"Spell the word that means: {word['simple_definition']}",
                "options": [], "answer": word["headword"], "input": "text",
                "hint": word["headword"][0] + "•" * (len(word["headword"]) - 1)}

    if mode == "fill_blank":
        example = word.get("easy_example") or word.get("example") or ""
        pattern = re.compile(re.escape(word["headword"]), re.IGNORECASE)
        blanked = pattern.sub("_____", example) if example else f"The word means {word['simple_definition']}: _____"
        distractors = rnd.sample(others, min(3, len(others)))
        options = [word["headword"]] + [d["headword"] for d in distractors]
        rnd.shuffle(options)
        return {**base, "prompt": f"Fill the blank:\n{blanked}",
                "options": options, "answer": word["headword"]}

    # fallback
    return build_question(word, "multiple_choice", pool)


def pick_mode(word: dict, progress: Optional[dict], pool: List[dict]) -> str:
    status = (progress or {}).get("status", "NEW")
    import random
    rnd = random.Random((progress or {}).get("times_seen", 0) + hash(word["id"]) % 1000)
    if status in ("NEW", "SEEN"):
        return "multiple_choice"
    if status == "LEARNING":
        choices = ["multiple_choice", "true_false"]
        if word.get("synonyms"):
            choices.append("synonym_select")
        return rnd.choice(choices)
    if status == "RECALLING":
        choices = ["fill_blank", "synonym_select" if word.get("synonyms") else "multiple_choice"]
        return rnd.choice(choices)
    return "spelling"

# ---------------------------------------------------------------------------
# auth routes
# ---------------------------------------------------------------------------


@api.post("/auth/register")
async def register(body: RegisterBody):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user_id = make_user_id()
    await db.users.insert_one({
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
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"token": token, "user": public_user(user)}


@api.post("/auth/login")
async def login(body: LoginBody):
    user = await db.users.find_one({"email": body.email.lower()})
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
    user = await db.users.find_one({"email": email})
    if not user:
        user_id = make_user_id()
        await db.users.insert_one({
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
        user = await db.users.find_one({"user_id": user_id})
    token = await create_session(user["user_id"])
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": public_user(user)}


@api.post("/auth/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        await db.user_sessions.delete_one({"session_token": auth[7:]})
    return {"ok": True}

# ---------------------------------------------------------------------------
# profile / onboarding
# ---------------------------------------------------------------------------


async def get_or_create_profile(user_id: str) -> dict:
    prof = await db.profiles.find_one({"user_id": user_id}, {"_id": 0})
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
        await db.profiles.insert_one(dict(prof))
    return prof


@api.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    prof = await get_or_create_profile(user["user_id"])
    prof.pop("_id", None)
    return {"user": public_user(user), "profile": prof}


@api.post("/onboarding")
async def onboarding(body: OnboardingBody, user: dict = Depends(get_current_user)):
    await get_or_create_profile(user["user_id"])
    await db.profiles.update_one({"user_id": user["user_id"]}, {"$set": {
        "reason": body.reason,
        "level": body.level,
        "daily_minutes": body.daily_minutes,
        "exam_slug": body.exam_slug,
        "exam_date": body.exam_date,
        "target_score": body.target_score,
        "updated_at": now_utc(),
    }})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"onboarded": True}})
    await log_event(user["user_id"], "onboarding_completed", {"reason": body.reason, "level": body.level})
    prof = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
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
    await db.profiles.update_one({"user_id": user["user_id"]}, {"$set": update})
    prof = await db.profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"profile": prof}

# ---------------------------------------------------------------------------
# words / knowledge graph
# ---------------------------------------------------------------------------


def word_public(w: dict) -> dict:
    w = dict(w)
    w.pop("_id", None)
    return w


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
    q: dict = {"status": "PUBLISHED"}
    if search:
        q["$or"] = [
            {"headword": {"$regex": search, "$options": "i"}},
            {"simple_definition": {"$regex": search, "$options": "i"}},
        ]
    if topic:
        q["topic"] = topic
    if cefr:
        q["cefr"] = cefr
    if exam:
        q["exam_relevance"] = exam
    total = await db.words.count_documents(q)
    cursor = db.words.find(q, {"_id": 0}).sort("headword", 1).skip(offset).limit(limit)
    words = await cursor.to_list(limit)
    # attach saved + progress status
    saved = {s["word_id"] for s in await db.saved_words.find({"user_id": user["user_id"]}, {"_id": 0, "word_id": 1}).to_list(1000)}
    prog = {p["word_id"]: p.get("status", "NEW") for p in await db.user_word_progress.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)}
    for w in words:
        w["saved"] = w["id"] in saved
        w["status"] = prog.get(w["id"], "NEW")
    return {"total": total, "words": words, "offset": offset, "limit": limit}


@api.get("/words/{word_id}")
async def word_detail(word_id: str, user: dict = Depends(get_current_user)):
    w = await db.words.find_one({"id": word_id}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")

    graph = await build_word_graph(db, w)
    exams = await db.exams.find({"slug": {"$in": w.get("exam_relevance", [])}}, {"_id": 0}).to_list(20)
    saved = await db.saved_words.find_one({"user_id": user["user_id"], "word_id": word_id})
    prog = await db.user_word_progress.find_one({"user_id": user["user_id"], "word_id": word_id}, {"_id": 0})
    await log_event(user["user_id"], "word_viewed", {"word_id": word_id})
    return {"word": w, "graph": graph, "exams": exams,
            "saved": bool(saved), "progress": prog}


@api.post("/words/{word_id}/save")
async def save_word(word_id: str, user: dict = Depends(get_current_user)):
    w = await db.words.find_one({"id": word_id})
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")
    await db.saved_words.update_one(
        {"user_id": user["user_id"], "word_id": word_id},
        {"$set": {"user_id": user["user_id"], "word_id": word_id, "created_at": now_utc()}},
        upsert=True,
    )
    await log_event(user["user_id"], "word_saved", {"word_id": word_id})
    return {"saved": True}


@api.delete("/words/{word_id}/save")
async def unsave_word(word_id: str, user: dict = Depends(get_current_user)):
    await db.saved_words.delete_one({"user_id": user["user_id"], "word_id": word_id})
    return {"saved": False}


@api.get("/saved")
async def saved_words(user: dict = Depends(get_current_user)):
    ids = [s["word_id"] for s in await db.saved_words.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)]
    words = await db.words.find({"id": {"$in": ids}}, {"_id": 0}).to_list(500)
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
    topics = await db.topics.find({}, {"_id": 0}).to_list(100)
    for t in topics:
        t["word_count"] = await db.words.count_documents({"topic": t["slug"], "status": "PUBLISHED"})
    return {"topics": topics}


@api.get("/exams")
async def get_exams(user: dict = Depends(get_current_user)):
    exams = await db.exams.find({}, {"_id": 0}).to_list(100)
    prof = await get_or_create_profile(user["user_id"])
    for e in exams:
        e["word_count"] = await db.words.count_documents({"exam_relevance": e["slug"], "status": "PUBLISHED"})
        e["active"] = prof.get("exam_slug") == e["slug"]
    return {"exams": exams, "active_exam": prof.get("exam_slug"), "exam_date": prof.get("exam_date"),
            "target_score": prof.get("target_score")}


@api.get("/exams/{slug}")
async def exam_detail(slug: str, user: dict = Depends(get_current_user)):
    exam = await db.exams.find_one({"slug": slug}, {"_id": 0})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    words = await db.words.find({"exam_relevance": slug, "status": "PUBLISHED"}, {"_id": 0}).to_list(500)
    prog = {p["word_id"]: p for p in await db.user_word_progress.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)}
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

    progresses = await db.user_word_progress.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(3000)
    seen_ids = {p["word_id"] for p in progresses}

    # due for review — ranked by the adaptive priority engine
    due = [p for p in progresses if ensure_aware(p.get("next_review_at")) and ensure_aware(p["next_review_at"]) <= now and p.get("status") != "MASTERED"]
    active_exam = prof.get("exam_slug")
    due_meta = {w["id"]: w for w in await db.words.find(
        {"id": {"$in": [p["word_id"] for p in due]}}, {"_id": 0}).to_list(3000)} if due else {}
    for p in due:
        pr = select_learning_priority(p, due_meta.get(p["word_id"], {}), now, active_exam)
        p["_priority"] = pr["priority"]
    due.sort(key=lambda p: -p["_priority"])
    due_ids = [p["word_id"] for p in due][:target]

    # new words filtered by exam/level
    q: dict = {"status": "PUBLISHED", "id": {"$nin": list(seen_ids)}}
    if prof.get("exam_slug"):
        q["exam_relevance"] = prof["exam_slug"]
    candidates = await db.words.find(q, {"_id": 0}).to_list(500)
    if not candidates and prof.get("exam_slug"):
        q.pop("exam_relevance", None)
        candidates = await db.words.find(q, {"_id": 0}).to_list(500)
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
    recent = await db.user_word_progress.find(
        {"user_id": user["user_id"], "status": {"$in": ["LEARNING", "RECALLING"]}}, {"_id": 0}
    ).sort("last_reviewed_at", -1).to_list(1)
    continue_word = None
    if recent:
        cw = await db.words.find_one({"id": recent[0]["word_id"]}, {"_id": 0})
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
        ws = await db.words.find({"exam_relevance": ref, "status": "PUBLISHED"}, {"_id": 0, "id": 1}).to_list(100)
        word_ids = [w["id"] for w in ws][:15]
    elif source == "topic" and ref:
        ws = await db.words.find({"topic": ref, "status": "PUBLISHED"}, {"_id": 0, "id": 1}).to_list(100)
        word_ids = [w["id"] for w in ws][:15]
    elif source == "word" and ref:
        word_ids = [ref]
    elif source == "list" and ref:
        tokens = [x for x in ref.split(",") if x][:15]
        word_ids = []
        for tk in tokens:
            wid = tk if await db.words.find_one({"id": tk}, {"_id": 1}) else await ensure_word(tk)
            if wid:
                word_ids.append(wid)
    elif source == "slipping":
        word_ids = await slipping_word_ids(user["user_id"])
    elif source == "saved":
        ws = await db.saved_words.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
        word_ids = [w["word_id"] for w in ws][:15]
    else:
        sel = await select_mission_words(user)
        word_ids = sel["due_ids"] + sel["new_ids"]

    if not word_ids:
        return {"questions": [], "count": 0}

    progresses = {p["word_id"]: p for p in await db.user_word_progress.find(
        {"user_id": user["user_id"], "word_id": {"$in": word_ids}}, {"_id": 0}).to_list(1000)}

    questions = []
    for wid in word_ids:
        w = pool_by_id.get(wid)
        if not w:
            continue
        mode = pick_mode(w, progresses.get(wid), pool)
        q = build_question(w, mode, pool)
        q["teach"] = progresses.get(wid, {}).get("status", "NEW") in ("NEW",) and source in ("mission", "exam", "topic")
        q["card"] = {
            "headword": w["headword"], "phonetic": w.get("phonetic"),
            "simple_definition": w["simple_definition"], "easy_meaning": w.get("easy_meaning"),
            "example": w.get("example"), "cefr": w.get("cefr"),
            "part_of_speech": w.get("part_of_speech"),
            "synonyms": w.get("synonyms", [])[:3],
        }
        questions.append(q)

    await log_event(user["user_id"], "learning_session_started", {"source": source, "count": len(questions)})
    return {"questions": questions, "count": len(questions), "source": source}


@api.post("/practice/answer")
async def practice_answer(body: AnswerBody, user: dict = Depends(get_current_user)):
    prev = await db.user_word_progress.find_one({"user_id": user["user_id"], "word_id": body.word_id}, {"_id": 0})
    word_meta = await db.words.find_one({"id": body.word_id}, {"_id": 0}) or {}
    updated = adaptive_update_progress(prev, body.correct, body.response_time_ms, word_meta, now_utc())
    updated_full = {"user_id": user["user_id"], "word_id": body.word_id, **updated}
    if not prev:
        updated_full["created_at"] = now_utc()
    was_mastered = prev and prev.get("status") == "MASTERED"
    await db.user_word_progress.update_one(
        {"user_id": user["user_id"], "word_id": body.word_id},
        {"$set": updated_full}, upsert=True,
    )
    xp_gain = 10 if body.correct else 2
    await db.profiles.update_one({"user_id": user["user_id"]}, {"$inc": {"xp": xp_gain}})
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"xp": xp_gain}})

    just_mastered = updated["status"] == "MASTERED" and not was_mastered
    if just_mastered:
        await log_event(user["user_id"], "word_mastered", {"word_id": body.word_id})
    await log_event(user["user_id"], "answer_submitted", {"word_id": body.word_id, "correct": body.correct, "mode": body.mode})

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
    streak = prof.get("streak", 0)
    if last != today:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        streak = streak + 1 if last == yesterday else 1
    longest = max(prof.get("longest_streak", 0), streak)
    await db.profiles.update_one({"user_id": user["user_id"]}, {"$set": {
        "streak": streak, "longest_streak": longest, "last_active_date": today,
    }})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"streak": streak}})
    await db.study_sessions.insert_one({
        "user_id": user["user_id"], "answered": body.answered, "correct": body.correct,
        "duration_ms": body.duration_ms, "source": body.source, "created_at": now_utc(),
    })
    await log_event(user["user_id"], "learning_session_completed",
                    {"answered": body.answered, "correct": body.correct, "source": body.source})
    return {"streak": streak, "longest_streak": longest}

# ---------------------------------------------------------------------------
# progress
# ---------------------------------------------------------------------------

XP_PER_LEVEL = 500


@api.get("/progress")
async def progress(user: dict = Depends(get_current_user)):
    prof = await get_or_create_profile(user["user_id"])
    progresses = await db.user_word_progress.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(5000)
    learned = sum(1 for p in progresses if p.get("status") in ("LEARNING", "RECALLING", "MASTERED"))
    mastered = sum(1 for p in progresses if p.get("status") == "MASTERED")
    total_correct = sum(p.get("times_correct", 0) for p in progresses)
    total_answered = sum(p.get("times_correct", 0) + p.get("times_wrong", 0) for p in progresses)
    accuracy = round(100 * total_correct / total_answered) if total_answered else 0

    # weak areas: topics with lowest avg mastery
    words = {w["id"]: w for w in await db.words.find({}, {"_id": 0, "id": 1, "topic": 1}).to_list(2000)}
    topic_scores: dict = {}
    for p in progresses:
        w = words.get(p["word_id"])
        if not w:
            continue
        topic_scores.setdefault(w["topic"], []).append(p.get("mastery_score", 0))
    weak = sorted(
        [{"topic": t, "avg_mastery": round(sum(v) / len(v))} for t, v in topic_scores.items() if v],
        key=lambda x: x["avg_mastery"])[:3]

    xp = prof.get("xp", 0)
    level = xp // XP_PER_LEVEL + 1
    sessions = await db.study_sessions.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    study_minutes = round(sum(s.get("duration_ms", 0) for s in sessions) / 60000)

    return {
        "words_learned": learned,
        "words_mastered": mastered,
        "accuracy": accuracy,
        "retention": accuracy,
        "streak": prof.get("streak", 0),
        "longest_streak": prof.get("longest_streak", 0),
        "xp": xp,
        "level": level,
        "xp_into_level": xp % XP_PER_LEVEL,
        "xp_per_level": XP_PER_LEVEL,
        "study_minutes": study_minutes,
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


async def log_event(user_id: str, event: str, props: dict):
    try:
        await db.analytics_events.insert_one({
            "user_id": user_id, "event": event, "props": props, "created_at": now_utc(),
        })
    except Exception:
        pass


@api.post("/analytics")
async def analytics(body: AnalyticsBody, user: dict = Depends(get_current_user)):
    await log_event(user["user_id"], body.event, body.props)
    return {"ok": True}


# ---------------------------------------------------------------------------
# entitlements / subscription
# ---------------------------------------------------------------------------


class SubscribeBody(BaseModel):
    plan: str = "monthly"


async def ai_coach_used_today(user_id: str) -> int:
    today = date.today().isoformat()
    return await db.ai_coach_usage.count_documents({"user_id": user_id, "date": today})


@api.get("/entitlements")
async def get_entitlements(user: dict = Depends(get_current_user)):
    tier = user.get("tier", "free")
    ent = entitlements_for(tier)
    return {
        "tier": tier,
        "is_pro": tier == "pro",
        "limits": ent,
        "ai_coach_used_today": await ai_coach_used_today(user["user_id"]),
    }


@api.post("/subscription/activate")
async def activate_subscription(body: SubscribeBody, user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"tier": "pro"}})
    await db.subscriptions.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "plan": body.plan, "status": "active",
                  "platform": "mock", "started_at": now_utc()}},
        upsert=True,
    )
    await log_event(user["user_id"], "subscription_started", {"plan": body.plan})
    return {"tier": "pro"}


@api.post("/subscription/cancel")
async def cancel_subscription(user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"tier": "free"}})
    await db.subscriptions.update_one({"user_id": user["user_id"]}, {"$set": {"status": "cancelled"}})
    await log_event(user["user_id"], "subscription_cancelled", {})
    return {"tier": "free"}


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
    existing = await db.tts_cache.find_one({"key": key}, {"_id": 1})
    if not existing:
        tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
        audio = await tts.generate_speech(text=clean_for_tts(text), model="tts-1", voice="alloy")
        await db.tts_cache.insert_one({"key": key, "audio": audio, "created_at": now_utc()})
    return key


@api.get("/tts/{key}.mp3")
async def serve_tts(key: str):
    doc = await db.tts_cache.find_one({"key": key})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=bytes(doc["audio"]), media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000"})


@api.get("/words/{word_id}/audio")
async def word_audio(word_id: str, user: dict = Depends(get_current_user)):
    w = await db.words.find_one({"id": word_id}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")
    if w.get("audio"):
        return w["audio"]

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
            tts_url = f"/tts/{key}.mp3"  # relative to /api; frontend prefixes with its own base
        except Exception:
            tts_url = None

    audio = {"us_url": us_url, "uk_url": uk_url, "tts_url": tts_url}
    await db.words.update_one({"id": word_id}, {"$set": {"audio": audio}})
    return audio


# ---------------------------------------------------------------------------
# AI Coach (gpt-5.6-luna) — supplementary, never overwrites canonical content
# ---------------------------------------------------------------------------


@api.post("/words/{word_id}/ai-coach")
async def ai_coach(word_id: str, user: dict = Depends(get_current_user)):
    w = await db.words.find_one({"id": word_id}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Word not found")

    cached = await db.ai_coach_content.find_one({"word_id": word_id}, {"_id": 0})
    if cached:
        return {"content": cached["content"], "provenance": "ai_generated", "cached": True}

    tier = user.get("tier", "free")
    ent = entitlements_for(tier)
    used = await ai_coach_used_today(user["user_id"])
    if used >= ent["ai_coach_per_day"]:
        raise HTTPException(status_code=402, detail="Daily AI Coach limit reached. Upgrade to Pro for unlimited.")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI is not configured")

    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"coach-{word_id}",
        system_message="You are a friendly, concise English vocabulary coach. Always return strict JSON.",
    ).with_model("openai", "gpt-5.6-luna")
    prompt = (
        f'For the English word "{w["headword"]}" (meaning: {w.get("simple_definition")}), '
        'return ONLY JSON: {"explanation":"a warm 2-sentence plain-English explanation a learner will remember",'
        '"example":"one fresh natural example sentence using the word","mnemonic":"a short vivid memory hook"}'
    )
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception:
        raise HTTPException(status_code=502, detail="AI Coach is busy, try again")

    text = resp if isinstance(resp, str) else str(resp)
    text = re.sub(r"^```(json)?|```$", "", text.strip()).strip()
    s, e = text.find("{"), text.rfind("}")
    content = None
    if s != -1 and e != -1:
        try:
            parsed = json.loads(text[s:e + 1])
            if all(isinstance(parsed.get(k), str) and parsed[k].strip() for k in ("explanation", "example", "mnemonic")):
                content = {k: parsed[k].strip() for k in ("explanation", "example", "mnemonic")}
        except Exception:
            content = None
    if not content:
        raise HTTPException(status_code=502, detail="Could not generate a good explanation, try again")

    await db.ai_coach_content.insert_one({"word_id": word_id, "content": content,
                                          "provenance": "ai_generated", "status": "PUBLISHED", "created_at": now_utc()})
    await db.ai_coach_usage.insert_one({"user_id": user["user_id"], "word_id": word_id, "date": date.today().isoformat(), "created_at": now_utc()})
    await log_event(user["user_id"], "ai_coach_generated", {"word_id": word_id})
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
    progresses = await db.user_word_progress.find(
        {"user_id": user_id, "status": {"$in": ["SEEN", "LEARNING", "RECALLING"]}}, {"_id": 0}
    ).to_list(3000)
    # candidate set: due soon (within horizon) and not yet solid — preserves the
    # existing nudge behavior; the adaptive slipping score is used for ranking.
    candidates = [p for p in progresses
                  if ensure_aware(p.get("next_review_at")) and ensure_aware(p["next_review_at"]) <= horizon
                  and p.get("mastery_score", 0) < 90]

    def rank(p):
        s = calculate_slipping(p, now)["slipping_score"]
        overdue = (now - ensure_aware(p["next_review_at"])).total_seconds()
        return (-s, -overdue, p.get("mastery_score", 0))
    candidates.sort(key=rank)
    return [p["word_id"] for p in candidates][:20]


@api.get("/review/slipping")
async def review_slipping(user: dict = Depends(get_current_user)):
    ids = await slipping_word_ids(user["user_id"])
    prog = {p["word_id"]: p for p in await db.user_word_progress.find(
        {"user_id": user["user_id"], "word_id": {"$in": ids}}, {"_id": 0}).to_list(100)}
    words = {w["id"]: w for w in await db.words.find({"id": {"$in": ids}}, {"_id": 0}).to_list(100)}
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
            "mastery_score": round(p.get("mastery_score", 0)),
            "overdue_days": overdue_days,
        })
    return {"count": len(items), "words": items}


@api.get("/articles")
async def list_articles(level: Optional[str] = None, topic: Optional[str] = None,
                        user: dict = Depends(get_current_user)):
    q: dict = {}
    if level:
        q["level"] = level
    if topic:
        q["topic"] = topic
    arts = await db.articles.find(q, {"_id": 0, "body": 0}).to_list(100)
    return {"articles": arts}


@api.get("/articles/{article_id}")
async def get_article(article_id: str, user: dict = Depends(get_current_user)):
    art = await db.articles.find_one({"id": article_id}, {"_id": 0})
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
    w = await db.words.find_one({"headword": norm}, {"_id": 0})
    if w:
        saved = await db.saved_words.find_one({"user_id": user["user_id"], "word_id": w["id"]})
        return {"in_bank": True, "id": w["id"], "headword": w["headword"],
                "phonetic": w.get("phonetic"), "simple_definition": w["simple_definition"],
                "example": w.get("example"), "cefr": w.get("cefr"),
                "part_of_speech": w.get("part_of_speech"), "saved": bool(saved)}
    d = await dictionary_lookup(norm)
    if not d:
        return {"in_bank": False, "headword": norm, "simple_definition": None, "found": False}
    return {"in_bank": False, "found": True, "headword": norm, **d, "saved": False}


async def ensure_word(headword: str) -> Optional[str]:
    """Return a word id for `headword`, creating an imported entry if needed.

    Dedupe against the canonical key so the same word (differing only by case or
    punctuation) never becomes a second canonical record.
    """
    norm = re.sub(r"[^a-z]", "", headword.lower())
    if not norm:
        return None
    ckey = normalize_headword(headword)
    existing = await db.words.find_one(
        {"$or": [{"canonical_key": ckey}, {"headword": norm}]}, {"_id": 0, "id": 1})
    if existing:
        return existing["id"]
    d = await dictionary_lookup(norm)
    if not d:
        return None
    raw = {"headword": norm, "cefr": "B1", "topic": "everyday", "frequency": 3,
           "academic_importance": 2, "easy_meaning": d.get("simple_definition"), **d}
    outcome = await ingest_word(db, raw, provenance="IMPORTED")
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
    bank = {w["headword"]: w for w in await db.words.find(
        {"headword": {"$in": candidates}}, {"_id": 0, "id": 1, "headword": 1, "simple_definition": 1, "cefr": 1}).to_list(200)}
    ids = [w["id"] for w in bank.values()]
    prog = {p["word_id"]: p.get("status", "NEW") for p in await db.user_word_progress.find(
        {"user_id": user_id, "word_id": {"$in": ids}}, {"_id": 0}).to_list(500)}
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
    # ensure all requested words exist (import non-bank ones), then build questions
    resolved: List[str] = []
    for token in body.word_ids[:20]:
        wid = token if await db.words.find_one({"id": token}, {"_id": 1}) else await ensure_word(token)
        if wid:
            resolved.append(wid)
    if not resolved:
        return {"questions": [], "count": 0}
    pool = await all_words_cache()
    pool_by_id = {w["id"]: w for w in pool}
    progresses = {p["word_id"]: p for p in await db.user_word_progress.find(
        {"user_id": user["user_id"], "word_id": {"$in": resolved}}, {"_id": 0}).to_list(200)}
    questions = []
    for wid in resolved:
        w = pool_by_id.get(wid)
        if not w:
            continue
        mode = pick_mode(w, progresses.get(wid), pool)
        q = build_question(w, mode, pool)
        q["teach"] = progresses.get(wid, {}).get("status", "NEW") == "NEW"
        q["card"] = {"headword": w["headword"], "phonetic": w.get("phonetic"),
                     "simple_definition": w["simple_definition"], "easy_meaning": w.get("easy_meaning"),
                     "example": w.get("example"), "cefr": w.get("cefr"),
                     "part_of_speech": w.get("part_of_speech"), "synonyms": w.get("synonyms", [])[:3]}
        questions.append(q)
    await log_event(user["user_id"], "learning_session_started", {"source": "import", "count": len(questions)})
    return {"questions": questions, "count": len(questions), "source": "import"}


@api.get("/")
async def root():
    return {"service": "vocabist", "status": "ok"}

# ---------------------------------------------------------------------------
# startup: indexes + seed
# ---------------------------------------------------------------------------


async def seed_content():
    if await db.words.count_documents({}) == 0:
        docs = []
        for w in WORDS:
            wid = slugify(w["headword"])
            docs.append({**w, "id": wid, "headword": w["headword"].lower(),
                         "status": "PUBLISHED", "provenance": "CURATED", "created_at": now_utc()})
        if docs:
            await db.words.insert_many(docs)
    if await db.topics.count_documents({}) == 0:
        await db.topics.insert_many([dict(t) for t in TOPICS])
    if await db.exams.count_documents({}) == 0:
        await db.exams.insert_many([dict(e) for e in EXAMS])
    if await db.articles.count_documents({}) == 0:
        await db.articles.insert_many([dict(a) for a in ARTICLES])

    # Merge AI-generated, validated word bank (idempotent upsert by id).
    bank_path = os.path.join(ROOT_DIR, "word_bank.json")
    if os.path.exists(bank_path):
        try:
            with open(bank_path) as f:
                bank = json.load(f)
        except Exception:
            bank = []
        for w in bank:
            hw = str(w.get("headword", "")).strip().lower()
            if not hw:
                continue
            wid = slugify(hw)
            if await db.words.find_one({"id": wid}, {"_id": 1}):
                continue
            await db.words.update_one(
                {"id": wid},
                {"$set": {**w, "id": wid, "headword": hw, "status": "PUBLISHED",
                          "provenance": "AI_GENERATED", "created_at": now_utc()}},
                upsert=True,
            )


async def migrate_canonical():
    """Idempotently upgrade every word to the canonical schema (Phase A).

    Preserves each word's existing ``id``, ``headword`` and all legacy fields;
    only computes ``canonical_key`` + ``relations`` (with canonical refs) and
    backfills structured ``meanings`` / ``pronunciation`` + optional placeholders.
    Words already at the current schema version are skipped, so re-runs are cheap.
    """
    all_words = await db.words.find({}, {"_id": 0}).to_list(200000)
    id_by_key: dict = {}
    for w in all_words:
        key = normalize_headword(w.get("headword", ""))
        if key and key not in id_by_key:
            id_by_key[key] = w["id"]

    pending = [w for w in all_words if w.get("schema_version") != 1 or not w.get("canonical_key")]
    migrated = 0
    for w in pending:
        try:
            await db.words.update_one({"id": w["id"]}, {"$set": to_canonical_storage(w, id_by_key)})
            migrated += 1
        except Exception as e:  # pragma: no cover
            print(f"[canonical] migrate failed for {w.get('id')}: {e}")
    if migrated:
        print(f"[canonical] migrated {migrated} word(s) to schema v1")


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("user_id")
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.words.create_index("id", unique=True)
    await db.words.create_index("headword")
    await db.words.create_index("topic")
    await db.words.create_index("cefr")
    await db.words.create_index("exam_relevance")
    await db.user_word_progress.create_index([("user_id", 1), ("word_id", 1)], unique=True)
    await db.user_word_progress.create_index([("user_id", 1), ("next_review_at", 1)])
    await db.saved_words.create_index([("user_id", 1), ("word_id", 1)], unique=True)
    await db.profiles.create_index("user_id", unique=True)
    await db.analytics_events.create_index("user_id")
    await seed_content()
    await migrate_canonical()
    await migrate_content_lifecycle(db)
    await resolve_all_relationship_refs(db)
    # Uniqueness safeguard against duplicate canonical words (after backfill).
    try:
        await db.words.create_index("canonical_key", unique=True)
    except Exception as e:  # pragma: no cover
        print(f"[canonical] canonical_key unique index skipped: {e}")


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
