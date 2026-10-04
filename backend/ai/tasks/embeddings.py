"""Embedding task — dedicated embedding provider interface (Nemotron Embed 1B).

Provides the clean integration point for the next semantic-search phase without
performing any database redesign in this phase.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..gateway import gateway


async def embed_passages(
    passages: List[str], *, prefer_model: Optional[str] = None, admin_id: Optional[str] = None,
) -> Dict[str, Any]:
    res = await gateway.run_embedding(passages, input_type="passage",
                                      prefer_model=prefer_model, admin_id=admin_id)
    vectors = res.data or []
    return {
        "count": len(vectors),
        "dimensions": len(vectors[0]) if vectors else 0,
        "vectors": vectors,
        "model_key": res.model_key,
        "provider": res.provider,
    }


async def embed_query(
    query: str, *, prefer_model: Optional[str] = None, admin_id: Optional[str] = None,
) -> Dict[str, Any]:
    res = await gateway.run_embedding([query], input_type="query",
                                      prefer_model=prefer_model, admin_id=admin_id)
    vectors = res.data or []
    return {
        "dimensions": len(vectors[0]) if vectors else 0,
        "vector": vectors[0] if vectors else [],
        "model_key": res.model_key,
        "provider": res.provider,
    }
