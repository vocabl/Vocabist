"""Multimodal (text + image) vocabulary extraction — Muse Glimmer primary.

The backend handles the model call; NVIDIA is never exposed to the client.
Extracted vocabulary is returned as raw canonical-shaped dicts for the EXISTING
review/validation pipeline — it is NOT auto-published.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import prompts
from ..gateway import gateway
from ..schemas import Task

_ALLOWED = {
    "headword", "cefr", "simple_definition", "example", "part_of_speech",
    "detected_context", "confidence", "reason",
}


def _clean(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    hw = str(raw.get("headword", "")).strip().lower()
    if not hw or len(hw) < 2:
        return None
    # Filter out non-vocabulary items
    if any(c.isdigit() for c in hw) and not hw.isalpha():
        return None
    out = {k: v for k, v in raw.items() if k in _ALLOWED and v is not None}
    out["headword"] = hw
    out["exam_relevance"] = []
    return out


async def extract_from_image(
    image_data_url: str, *, max_words: int = 15, instruction: str = "",
    prefer_model: Optional[str] = None, admin_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    user_text = prompts.multimodal_extract_prompt(max_words)
    if instruction:
        user_text = f"{instruction}\n\n{user_text}"
    messages = [
        {"role": "system", "content": prompts.multimodal_extract_system()},
        {"role": "user", "content": user_text},
    ]
    res = await gateway.run_json(
        Task.MULTIMODAL_LEARNING, messages, images=[image_data_url], max_tokens=2000,
        prefer_model=prefer_model, admin_id=admin_id, user_id=user_id,
    )
    data = res.data
    rows = data.get("words") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    entries: List[Dict[str, Any]] = []
    for r in (rows or []):
        c = _clean(r)
        if c:
            entries.append(c)
    return {
        "entries": entries,
        "model_key": res.model_key,
        "provider": res.provider,
        "fallback_used": res.fallback_used,
    }
