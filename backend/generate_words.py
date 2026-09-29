"""One-off AI generation of a large, validated vocabulary bank.

Uses the Emergent universal key (gpt-5.6-luna) to produce structured word entries,
validates each against the required schema, dedupes, and writes word_bank.json.
This is content generation with provenance = 'ai_generated' — server.py seeds it as
PUBLISHED canonical content only after this validation step.
"""
import os
import re
import json
import asyncio
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
KEY = os.environ["EMERGENT_LLM_KEY"]

TOPICS = ["academic", "everyday", "business", "science", "emotions", "society"]
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
EXAMS = ["ielts", "toefl", "gre", "sat", "gmat", "cefr"]

REQUIRED = ["headword", "phonetic", "part_of_speech", "cefr", "simple_definition",
            "easy_meaning", "example", "synonyms", "antonyms", "topic", "exam_relevance"]

SCHEMA = """Return ONLY a valid JSON array (no markdown, no prose). Each element:
{
 "headword": "single lowercase english word",
 "phonetic": "/IPA/",
 "part_of_speech": "noun|verb|adjective|adverb",
 "cefr": "A1|A2|B1|B2|C1|C2",
 "simple_definition": "one clear sentence",
 "easy_meaning": "2-4 word plain meaning",
 "detailed_definition": "one richer sentence",
 "example": "natural example sentence using the word",
 "easy_example": "very simple example sentence",
 "synonyms": ["w1","w2","w3"],
 "antonyms": ["w1","w2"],
 "related": ["w1","w2"],
 "word_family": ["w1"],
 "roots": ["latin/greek root (meaning)"],
 "prefixes": [],
 "suffixes": [],
 "mnemonic": "short memory hook",
 "common_mistakes": "one common confusion",
 "usage_notes": "short note",
 "topic": "academic|everyday|business|science|emotions|society",
 "exam_relevance": ["ielts","toefl","gre","sat","gmat"],
 "frequency": 3,
 "academic_importance": 3
}"""


def valid(w):
    if not isinstance(w, dict):
        return False
    for k in REQUIRED:
        if k not in w or w[k] in (None, "", []):
            if k in ("synonyms", "antonyms", "exam_relevance"):
                w[k] = w.get(k) or []
                continue
            return False
    hw = str(w["headword"]).strip().lower()
    if not re.fullmatch(r"[a-z][a-z\-]{1,20}", hw):
        return False
    w["headword"] = hw
    if w.get("cefr") not in LEVELS:
        return False
    if w.get("topic") not in TOPICS:
        w["topic"] = "everyday"
    w["exam_relevance"] = [e for e in (w.get("exam_relevance") or []) if e in EXAMS]
    for arr in ["synonyms", "antonyms", "related", "word_family", "roots", "prefixes", "suffixes"]:
        w[arr] = [str(x).strip() for x in (w.get(arr) or []) if str(x).strip()]
    return True


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return []


async def gen_batch(level, topic, count, existing):
    chat = LlmChat(
        api_key=KEY,
        session_id=f"wordbank-{level}-{topic}",
        system_message="You are a lexicographer creating accurate CEFR-aligned English vocabulary data for a learning app. Be factually correct; never invent fake words.",
    ).with_model("openai", "gpt-5.6-luna")
    avoid = ", ".join(sorted(existing)[:120])
    prompt = (
        f"Generate {count} distinct, real, useful English words at CEFR level {level}, "
        f"themed around '{topic}', that commonly appear in exams. "
        f"Do NOT reuse any of these already-used words: {avoid}.\n\n{SCHEMA}"
    )
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        print(f"  [{level}/{topic}] error: {e}")
        return []
    items = parse_json(resp if isinstance(resp, str) else str(resp))
    out = []
    for w in items:
        if valid(w) and w["headword"] not in existing:
            existing.add(w["headword"])
            w["cefr"] = level
            out.append(w)
    print(f"  [{level}/{topic}] +{len(out)} (total {len(existing)})")
    return out


async def main():
    all_words = []
    existing = set()
    # seed headwords to avoid duplicating the base bank
    try:
        from seed_data import WORDS as BASE
        for b in BASE:
            existing.add(b["headword"].lower())
    except Exception:
        pass

    plan = []
    for level in LEVELS:
        for topic in TOPICS:
            plan.append((level, topic, 6))  # 36 batches x ~6 = ~200 words

    for level, topic, count in plan:
        batch = await gen_batch(level, topic, count, existing)
        all_words.extend(batch)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "word_bank.json"), "w") as f:
            json.dump(all_words, f, indent=1)

    print(f"DONE: {len(all_words)} words written to word_bank.json")


if __name__ == "__main__":
    asyncio.run(main())
