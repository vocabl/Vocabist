"""Vocabulary generation task.

Produces canonical-shaped raw word dicts via the gateway, ready to be fed into
the EXISTING Vocabist content ingestion/validation pipeline (content_ingest.
ingest_word with provenance=AI_GENERATED → REVIEW). We do NOT invent a second
vocabulary schema here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import prompts
from ..gateway import gateway
from ..schemas import Task

_ALLOWED_FIELDS = {
    "headword", "part_of_speech", "cefr", "simple_definition", "easy_meaning",
    "example", "easy_example", "synonyms", "antonyms", "related", "word_family",
    "mnemonic", "common_mistakes", "usage_notes", "topic", "exam_relevance",
}


def _clean_entry(raw: Dict[str, Any], exam: Optional[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    hw = str(raw.get("headword", "")).strip()
    if not hw:
        return None
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if k in _ALLOWED_FIELDS and v is not None:
            out[k] = v
    out["headword"] = hw
    # never let the model invent exam refs
    if exam:
        out["exam_relevance"] = [exam]
    else:
        out["exam_relevance"] = []
    return out


async def generate(
    count: int,
    *,
    cefr: Optional[str] = None,
    topic: Optional[str] = None,
    part_of_speech: Optional[str] = None,
    exam: Optional[str] = None,
    vocabulary_type: Optional[str] = None,
    enrichment_level: str = "standard",
    avoid: Optional[List[str]] = None,
    prefer_model: Optional[str] = None,
    admin_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return {entries, model_key, provider, fallback_used, attempts, raw_count}."""
    messages = [
        {"role": "system", "content": prompts.vocab_generation_system()},
        {"role": "user", "content": prompts.vocab_generation_prompt(
            count, cefr=cefr, topic=topic, part_of_speech=part_of_speech, exam=exam,
            vocabulary_type=vocabulary_type, avoid=avoid, enrichment_level=enrichment_level,
        )},
    ]
    # generous budget: reasoning models + many entries
    max_tokens = min(8000, 400 + count * 120)
    res = await gateway.run_json(
        Task.VOCABULARY_GENERATION, messages, max_tokens=max_tokens,
        prefer_model=prefer_model, admin_id=admin_id, job_id=job_id,
    )
    data = res.data
    rows = data.get("words") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    entries = []
    for r in (rows or []):
        c = _clean_entry(r, exam)
        if c:
            entries.append(c)
    return {
        "entries": entries,
        "raw_count": len(rows or []),
        "model_key": res.model_key,
        "provider": res.provider,
        "model_id": res.model_id,
        "fallback_used": res.fallback_used,
        "attempts": res.attempts,
    }
