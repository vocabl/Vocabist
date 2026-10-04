"""Vocabist AI Gateway — the single entry point for all AI operations.

    run_chat / run_json / run_embedding / run_translation

Responsibilities:
  - resolve the capability-valid, enabled model chain for a task
  - attempt models in order with intelligent fallback (timeout/429/5xx/conn/
    unavailable/malformed) — never blind fallback on auth/bad-request
  - parse + optionally validate structured JSON output
  - record centralized usage and update live model status (no faked health)
"""
from __future__ import annotations

import re
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import registry, router, usage, state_store
from .providers import get_provider
from .errors import AIError, NoModelAvailable, MalformedOutput, ConfigurationError
from .schemas import ModelStatus, Task


@dataclass
class GatewayResult:
    ok: bool
    task: str
    text: str = ""
    data: Any = None
    model_key: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    fallback_used: bool = False
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)
    request_id: str = ""


_FENCE_RE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


def extract_json(text: str) -> Any:
    """Best-effort structured-output extraction. Raises MalformedOutput on failure."""
    if not text:
        raise MalformedOutput("empty model output")
    cleaned = _FENCE_RE.sub("", text).strip()
    # try whole string first
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # find the widest {...} or [...] span
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = cleaned.find(open_c), cleaned.rfind(close_c)
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(cleaned[s:e + 1])
            except Exception:
                continue
    raise MalformedOutput("could not parse JSON from model output")


class Gateway:
    async def _update_status(self, spec, *, success: bool, latency_ms: int, error: str = "") -> None:
        patch: Dict[str, Any] = {"last_latency_ms": latency_ms}
        if success:
            patch["status"] = ModelStatus.AVAILABLE
            patch["last_success"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            patch["last_error"] = ""
            patch["failure_count"] = 0
        else:
            patch["status"] = ModelStatus.UNAVAILABLE
            patch["last_error"] = error[:200]
            cfg = await state_store.load_config()
            cur = cfg.get("models", {}).get(spec.key, {})
            patch["failure_count"] = int(cur.get("failure_count", 0)) + 1
        await state_store.update_model_state(spec.key, patch)

    # ------------------------------------------------------------------ #
    # CHAT (optionally expecting JSON)
    # ------------------------------------------------------------------ #
    async def run_chat(
        self,
        task: str,
        messages: List[Dict[str, Any]],
        *,
        expect_json: bool = False,
        temperature: Optional[float] = None,
        max_tokens: int = 1500,
        images: Optional[List[str]] = None,
        prefer_model: Optional[str] = None,
        user_id: Optional[str] = None,
        admin_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> GatewayResult:
        cfg = await state_store.load_config()
        chain = router.resolve_chain(task, cfg, prefer_model)
        request_id = uuid.uuid4().hex
        attempts: List[Dict[str, Any]] = []

        if not chain:
            raise NoModelAvailable(f"no enabled/capable model for task '{task}'")

        for i, spec in enumerate(chain):
            # vision guard: only route images to vision-capable models
            use_images = images if (images and "vision" in spec.capabilities) else None
            provider = get_provider(spec.provider)
            start = time.monotonic()
            try:
                out = await provider.chat(
                    spec, messages, temperature=temperature, max_tokens=max_tokens,
                    expect_json=expect_json, images=use_images,
                )
                data = None
                if expect_json:
                    data = extract_json(out["text"])  # may raise MalformedOutput → fallback
                latency = int((time.monotonic() - start) * 1000)
                await self._update_status(spec, success=True, latency_ms=latency)
                await usage.record(
                    task=task, provider=spec.provider, model=spec.key, success=True,
                    latency_ms=latency, fallback=(i > 0), attempt=i, usage=out.get("usage"),
                    user_id=user_id, admin_id=admin_id, job_id=job_id, request_id=request_id,
                )
                return GatewayResult(
                    ok=True, task=task, text=out["text"], data=data, model_key=spec.key,
                    provider=spec.provider, model_id=spec.model_id, fallback_used=(i > 0),
                    attempts=attempts, usage=out.get("usage") or {}, request_id=request_id,
                )
            except AIError as e:
                latency = int((time.monotonic() - start) * 1000)
                await self._update_status(spec, success=False, latency_ms=latency, error=e.message)
                await usage.record(
                    task=task, provider=spec.provider, model=spec.key, success=False,
                    latency_ms=latency, fallback=(i > 0), attempt=i, error_code=e.code,
                    user_id=user_id, admin_id=admin_id, job_id=job_id, request_id=request_id,
                )
                attempts.append({
                    "model": spec.key, "provider": spec.provider, "reason": e.code,
                    "detail": e.detail, "attempt": i,
                })
                if not e.fallbackable:
                    # non-recoverable for the whole chain (auth/bad request/config)
                    if isinstance(e, ConfigurationError):
                        continue  # a missing key on one provider shouldn't kill the chain
                    break
                continue

        raise NoModelAvailable(f"all models failed for task '{task}'")

    async def run_json(self, task: str, messages: List[Dict[str, Any]], **kw) -> GatewayResult:
        return await self.run_chat(task, messages, expect_json=True, **kw)

    # ------------------------------------------------------------------ #
    # EMBEDDINGS
    # ------------------------------------------------------------------ #
    async def run_embedding(
        self, inputs: List[str], *, input_type: str = "passage",
        prefer_model: Optional[str] = None, user_id: Optional[str] = None,
        admin_id: Optional[str] = None,
    ) -> GatewayResult:
        task = Task.SEMANTIC_EMBEDDING
        cfg = await state_store.load_config()
        chain = router.resolve_chain(task, cfg, prefer_model)
        request_id = uuid.uuid4().hex
        attempts: List[Dict[str, Any]] = []
        if not chain:
            raise NoModelAvailable("no enabled embedding model")
        for i, spec in enumerate(chain):
            provider = get_provider(spec.provider)
            start = time.monotonic()
            try:
                out = await provider.embed(spec, inputs, input_type=input_type)
                latency = int((time.monotonic() - start) * 1000)
                await self._update_status(spec, success=True, latency_ms=latency)
                await usage.record(
                    task=task, provider=spec.provider, model=spec.key, success=True,
                    latency_ms=latency, fallback=(i > 0), attempt=i, usage=out.get("usage"),
                    user_id=user_id, admin_id=admin_id, request_id=request_id,
                )
                return GatewayResult(
                    ok=True, task=task, data=out["vectors"], model_key=spec.key,
                    provider=spec.provider, model_id=spec.model_id, fallback_used=(i > 0),
                    attempts=attempts, usage=out.get("usage") or {}, request_id=request_id,
                )
            except AIError as e:
                latency = int((time.monotonic() - start) * 1000)
                await self._update_status(spec, success=False, latency_ms=latency, error=e.message)
                await usage.record(
                    task=task, provider=spec.provider, model=spec.key, success=False,
                    latency_ms=latency, fallback=(i > 0), attempt=i, error_code=e.code,
                    user_id=user_id, admin_id=admin_id, request_id=request_id,
                )
                attempts.append({"model": spec.key, "reason": e.code, "attempt": i})
                if not e.fallbackable and not isinstance(e, ConfigurationError):
                    break
                continue
        raise NoModelAvailable("all embedding models failed")

    # ------------------------------------------------------------------ #
    # TRANSLATION
    # ------------------------------------------------------------------ #
    async def run_translation(
        self, text: str, *, source_language: str, target_language: str,
        prefer_model: Optional[str] = None, user_id: Optional[str] = None,
        admin_id: Optional[str] = None,
    ) -> GatewayResult:
        from . import prompts
        messages = [
            {"role": "system", "content": prompts.translate_system(source_language, target_language)},
            {"role": "user", "content": text},
        ]
        res = await self.run_chat(
            Task.TRANSLATION, messages, expect_json=False, max_tokens=800,
            prefer_model=prefer_model, user_id=user_id, admin_id=admin_id,
        )
        return res

    # ------------------------------------------------------------------ #
    # PING — real availability probe (updates live status, never faked)
    # ------------------------------------------------------------------ #
    async def ping(self, model_key: str) -> Dict[str, Any]:
        spec = registry.get_model(model_key)
        if not spec:
            return {"model": model_key, "status": "UNKNOWN", "error": "unknown model"}
        provider = get_provider(spec.provider)
        start = time.monotonic()
        try:
            if "embedding" in spec.capabilities:
                await provider.embed(spec, ["ping"], input_type="query")
            elif "translation" in spec.capabilities:
                await provider.chat(spec, [{"role": "user", "content": "Translate to French: hello"}], max_tokens=20)
            else:
                await provider.chat(spec, [{"role": "user", "content": "Reply with: ok"}], max_tokens=20)
            latency = int((time.monotonic() - start) * 1000)
            await self._update_status(spec, success=True, latency_ms=latency)
            return {"model": model_key, "status": ModelStatus.AVAILABLE, "latency_ms": latency}
        except AIError as e:
            latency = int((time.monotonic() - start) * 1000)
            await self._update_status(spec, success=False, latency_ms=latency, error=e.message)
            return {"model": model_key, "status": ModelStatus.UNAVAILABLE, "error": e.code, "detail": e.detail}


gateway = Gateway()
