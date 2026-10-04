"""Field-level enrichment / regeneration for a single vocabulary entry."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .. import prompts
from ..gateway import gateway
from ..schemas import Task
from ..errors import MalformedOutput

_ARRAY_FIELDS = {"synonyms", "antonyms", "word_family"}
_CEFR = {"A1", "A2", "B1", "B2", "C1", "C2"}


async def regenerate_field(
    word: Dict[str, Any], field: str, *, prefer_model: Optional[str] = None,
    admin_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return {field, json_key, value, model_key, provider, fallback_used}."""
    spec = prompts.enrich_field_spec(field)
    if not spec:
        raise MalformedOutput(f"unsupported field '{field}'")
    json_key, _ = spec
    prompt = prompts.enrich_field_prompt(field, word)
    messages = [
        {"role": "system", "content": prompts.enrich_field_system()},
        {"role": "user", "content": prompt},
    ]
    res = await gateway.run_json(
        Task.VOCABULARY_ENRICHMENT, messages, max_tokens=600,
        prefer_model=prefer_model, admin_id=admin_id,
    )
    data = res.data if isinstance(res.data, dict) else {}
    value = data.get(json_key)

    # normalize + validate
    if field in _ARRAY_FIELDS:
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list):
            raise MalformedOutput(f"expected array for '{field}'")
        value = [str(v).strip() for v in value if str(v).strip()]
    elif field == "cefr":
        value = str(value or "").strip().upper()
        if value not in _CEFR:
            raise MalformedOutput(f"invalid CEFR '{value}'")
    else:
        value = str(value or "").strip()
        if not value:
            raise MalformedOutput(f"empty value for '{field}'")

    return {
        "field": field,
        "json_key": json_key,
        "value": value,
        "model_key": res.model_key,
        "provider": res.provider,
        "fallback_used": res.fallback_used,
    }
