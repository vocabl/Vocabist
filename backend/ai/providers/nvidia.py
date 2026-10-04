"""NVIDIA hosted API provider (OpenAI-compatible).

Base URL : https://integrate.api.nvidia.com/v1
Chat     : POST /chat/completions
Embeddings: POST /embeddings  (input_type: passage | query)

The NVIDIA_API_KEY is backend-only and is never returned to callers or logged.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseProvider
from ..registry import ModelSpec
from ..errors import (
    ConfigurationError, AuthError, ModelUnavailable, RateLimited,
    ProviderServerError, TimeoutError_, ConnectionError_, BadRequest,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _base_url() -> str:
    return os.environ.get("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")


def _api_key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "")


def _strip_reasoning(text: str) -> str:
    if not text:
        return ""
    return _THINK_RE.sub("", text).strip()


def _raise_for_status(status: int, body: str) -> None:
    snippet = (body or "")[:300]
    if status in (401, 403):
        raise AuthError("NVIDIA auth failed", detail=snippet)
    if status == 404:
        raise ModelUnavailable("model not found on endpoint", detail=snippet)
    if status == 429:
        raise RateLimited("NVIDIA rate limited", detail=snippet)
    if status == 400:
        raise BadRequest("bad request to NVIDIA", detail=snippet)
    if status >= 500:
        raise ProviderServerError(f"NVIDIA server error {status}", detail=snippet)
    if status >= 400:
        raise ModelUnavailable(f"NVIDIA error {status}", detail=snippet)


class NvidiaProvider(BaseProvider):
    name = "nvidia"

    async def _post(self, path: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        key = _api_key()
        if not key:
            raise ConfigurationError("NVIDIA_API_KEY is not configured")
        url = f"{_base_url()}{path}"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException:
            raise TimeoutError_("NVIDIA request timed out")
        except httpx.HTTPError as e:
            raise ConnectionError_(f"NVIDIA connection error: {type(e).__name__}")
        if resp.status_code >= 400:
            _raise_for_status(resp.status_code, resp.text)
        try:
            return resp.json()
        except Exception:
            raise ProviderServerError("NVIDIA returned non-JSON response")

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
        msgs = [dict(m) for m in messages]

        # Nemotron reasoning models: keep structured-generation output clean.
        if expect_json and "reasoning" in spec.capabilities and spec.provider == "nvidia":
            if not msgs or msgs[0].get("role") != "system":
                msgs.insert(0, {"role": "system", "content": "detailed thinking off"})
            else:
                msgs[0]["content"] = "detailed thinking off\n" + str(msgs[0]["content"])

        # Multimodal: attach images to the last user message (OpenAI vision format).
        if images:
            last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
            if last_user is not None:
                content = [{"type": "text", "text": str(last_user.get("content", ""))}]
                for img in images:
                    content.append({"type": "image_url", "image_url": {"url": img}})
                last_user["content"] = content

        payload: Dict[str, Any] = {
            "model": spec.model_id,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": spec.default_temperature if temperature is None else temperature,
            "stream": False,
        }
        data = await self._post("/chat/completions", payload, timeout=120.0)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderServerError("NVIDIA chat returned no choices")
        message = choices[0].get("message", {}) or {}
        text = message.get("content") or ""
        text = _strip_reasoning(text)
        if not text and message.get("reasoning_content"):
            text = _strip_reasoning(message["reasoning_content"])
        return {
            "text": text,
            "usage": data.get("usage") or {},
            "raw": {"finish_reason": choices[0].get("finish_reason")},
        }

    async def embed(
        self, spec: ModelSpec, inputs: List[str], input_type: str = "passage",
    ) -> Dict[str, Any]:
        payload = {
            "model": spec.model_id,
            "input": inputs,
            "input_type": "query" if input_type == "query" else "passage",
            "encoding_format": "float",
        }
        data = await self._post("/embeddings", payload, timeout=60.0)
        rows = data.get("data") or []
        vectors = [r.get("embedding") for r in rows]
        return {"vectors": vectors, "usage": data.get("usage") or {}}
