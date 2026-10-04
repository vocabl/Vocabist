"""Provider interface. Concrete providers: NvidiaProvider, EmergentProvider."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..registry import ModelSpec


class BaseProvider:
    name = "base"

    async def chat(
        self,
        spec: ModelSpec,
        messages: List[Dict[str, Any]],
        *,
        temperature: Optional[float] = None,
        max_tokens: int = 1500,
        expect_json: bool = False,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return {text:str, usage:dict, raw:dict}. Raise ai.errors.AIError on failure."""
        raise NotImplementedError

    async def embed(
        self, spec: ModelSpec, inputs: List[str], input_type: str = "passage",
    ) -> Dict[str, Any]:
        """Return {vectors:List[List[float]], usage:dict}."""
        raise NotImplementedError
