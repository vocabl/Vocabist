"""Translation task — dedicated capability via the gateway (Riva primary)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..gateway import gateway


async def translate(
    text: str, *, source_language: str = "en", target_language: str,
    prefer_model: Optional[str] = None, admin_id: Optional[str] = None,
) -> Dict[str, Any]:
    res = await gateway.run_translation(
        text, source_language=source_language, target_language=target_language,
        prefer_model=prefer_model, admin_id=admin_id,
    )
    return {
        "source_language": source_language,
        "target_language": target_language,
        "input": text,
        "translation": (res.text or "").strip(),
        "model_key": res.model_key,
        "provider": res.provider,
        "fallback_used": res.fallback_used,
    }
