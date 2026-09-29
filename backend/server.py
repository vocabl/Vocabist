"""Vocably backend — FastAPI + MongoDB (Motor).

Implements Phase 1–3: auth (email/password + Emergent Google), profile /
onboarding, vocabulary engine, word detail + knowledge graph, saved words,
daily mission, adaptive spaced-review practice engine, progress / streak / XP,
entitlements and analytics events.
"""
import os
import re
import secrets
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Any

import httpx
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from dotenv import load_dotenv

from seed_data import WORDS, TOPICS, EXAMS

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "vocably")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Vocably API")
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
# spaced review engine (deterministic, upgradeable)
# ---------------------------------------------------------------------------

INTERVALS_DAYS = [0, 1, 3, 7, 16, 35, 70]  # by consecutive_correct index


def status_from_mastery(score: float, consecutive: int) -> str:
    if score >= 90 and consecutive >= 4:
        return "MASTERED"
    if score >= 60:
        return "RECALLING"
    if score >= 25:
        return "LEARNING"
    if score > 0:
        return "SEEN"
    return "NEW"


def compute_review(prev: Optional[dict], correct: bool, response_time_ms: int) -> dict:
    p = prev or {}
    times_seen = p.get("times_seen", 0) + 1
    times_correct = p.get("times_correct", 0) + (1 if correct else 0)
    times_wrong = p.get("times_wrong", 0) + (0 if correct else 1)
    consecutive = p.get("consecutive_correct", 0)
    mastery = float(p.get("mastery_score", 0))
    confidence = float(p.get("confidence_score", 0))

    if correct:
        consecutive += 1
        gain = 18 if response_time_ms and response_time_ms < 6000 else 12
        mastery = min(100.0, mastery + gain)
        confidence = min(100.0, confidence + 15)
    else:
        consecutive = 0
        mastery = max(0.0, mastery - 20)
        confidence = max(0.0, confidence - 25)

    idx = min(consecutive, len(INTERVALS_DAYS) - 1)
    interval_days = INTERVALS_DAYS[idx] if correct else 0
    if not correct:
        next_review = now_utc() + timedelta(minutes=10)
    elif interval_days == 0:
        next_review = now_utc() + timedelta(hours=8)
    else:
        next_review = now_utc() + timedelta(days=interval_days)

    prev_avg = p.get("average_response_time", 0) or 0
    avg_rt = response_time_ms if not prev_avg else int((prev_avg + response_time_ms) / 2)

    return {
        "times_seen": times_seen,
        "times_correct": times_correct,
        "times_wrong": times_wrong,
        "consecutive_correct": consecutive,
        "mastery_score": round(mastery, 1),
        "confidence_score": round(confidence, 1),
        "review_interval": interval_days,
        "last_reviewed_at": now_utc(),
        "next_review_at": next_review,
        "average_response_time": avg_rt,
        "status": status_from_mastery(mastery, consecutive),
        "updated_at": now_utc(),
    }

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

    async def resolve(names: List[str]) -> List[dict]:
        out = []
        for n in names or []:
            match = await db.words.find_one({"headword": n.lower()}, {"_id": 0, "id": 1, "headword": 1, "cefr": 1, "simple_definition": 1})
            out.append(match if match else {"headword": n, "id": None})
        return out

    graph = {
        "synonyms": await resolve(w.get("synonyms", [])),
        "antonyms": await resolve(w.get("antonyms", [])),
        "related": await resolve(w.get("related", [])),
    }
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

    # due for review
    due = [p for p in progresses if ensure_aware(p.get("next_review_at")) and ensure_aware(p["next_review_at"]) <= now and p.get("status") != "MASTERED"]

    def due_priority(p):
        overdue = (now - ensure_aware(p["next_review_at"])).total_seconds()
        exam_boost = 0
        return (-p.get("mastery_score", 0), -overdue, exam_boost)
    due.sort(key=due_priority)
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
        ws = await db.words.find({"exam_relevance": ref, "status": "PUBLISHED"}, {"_id": 0, "id": 1}).to_list(100)
        word_ids = [w["id"] for w in ws][:15]
    elif source == "topic" and ref:
        ws = await db.words.find({"topic": ref, "status": "PUBLISHED"}, {"_id": 0, "id": 1}).to_list(100)
        word_ids = [w["id"] for w in ws][:15]
    elif source == "word" and ref:
        word_ids = [ref]
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
    updated = compute_review(prev, body.correct, body.response_time_ms)
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
            "xp_gain": xp_gain, "just_mastered": just_mastered,
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


@api.get("/")
async def root():
    return {"service": "vocably", "status": "ok"}

# ---------------------------------------------------------------------------
# startup: indexes + seed
# ---------------------------------------------------------------------------


async def seed_content():
    if await db.words.count_documents({}) == 0:
        docs = []
        for w in WORDS:
            wid = slugify(w["headword"])
            docs.append({**w, "id": wid, "headword": w["headword"].lower(),
                         "status": "PUBLISHED", "provenance": "seed", "created_at": now_utc()})
        if docs:
            await db.words.insert_many(docs)
    if await db.topics.count_documents({}) == 0:
        await db.topics.insert_many([dict(t) for t in TOPICS])
    if await db.exams.count_documents({}) == 0:
        await db.exams.insert_many([dict(e) for e in EXAMS])


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


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
