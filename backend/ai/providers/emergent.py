"""Emergent Universal LLM provider (existing GPT-5.6 Luna integration).

Wraps emergentintegrations.LlmChat so the existing AI Coach and gateway
fallbacks flow through the same abstraction. Chat only — not an embedding or
translation provider.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from .base import BaseProvider
from ..registry import ModelSpec
from ..errors import ConfigurationError, ProviderServerError, ModelUnavailable


class EmergentProvider(BaseProvider):
    name = "emergent"

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
        key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not key:
            raise ConfigurationError("EMERGENT_LLM_KEY is not configured")

        from emergentintegrations.llm.chat import LlmChat, UserMessage

        system = next((m.get("content") for m in messages if m.get("role") == "system"), None)
        user_parts = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
        user_text = "\n\n".join(p for p in user_parts if p) or "Hello"

        chat = LlmChat(
            api_key=key,
            session_id=f"gw-{uuid.uuid4().hex[:12]}",
            system_message=str(system or "You are a helpful assistant. Reply concisely."),
        ).with_model("openai", spec.model_id)

        try:
            resp = await chat.send_message(UserMessage(text=user_text))
        except Exception as e:  # noqa: BLE001
            raise ProviderServerError(f"Emergent provider error: {type(e).__name__}")

        text = resp if isinstance(resp, str) else str(resp)
        return {"text": text.strip(), "usage": {}, "raw": {}}

    async def embed(self, spec: ModelSpec, inputs: List[str], input_type: str = "passage") -> Dict[str, Any]:
        raise ModelUnavailable("Emergent provider does not support embeddings")
