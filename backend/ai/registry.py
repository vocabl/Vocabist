"""Centralized model registry.

Each model declares provider, model_id, capabilities, modality, default params
and a human display name. Enable/disable + live availability status are layered
on top from the persistent config store (state_store).

Model availability is NEVER faked: a model's runtime status starts UNKNOWN (or
DISABLED if its provider has no API key) and only moves to AVAILABLE/UNAVAILABLE
after a real provider call or explicit ping updates it.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .schemas import Capability, Modality, ModelStatus


class ModelSpec:
    def __init__(
        self,
        key: str,
        provider: str,
        model_id: str,
        display_name: str,
        capabilities: List[str],
        modality: str,
        *,
        enabled: bool = True,
        default_temperature: Optional[float] = None,
        context: Optional[str] = None,
        notes: str = "",
    ):
        self.key = key
        self.provider = provider
        self.model_id = model_id
        self.display_name = display_name
        self.capabilities = capabilities
        self.modality = modality
        self.enabled = enabled
        self.default_temperature = default_temperature
        self.context = context
        self.notes = notes

    def has(self, cap: str) -> bool:
        return cap in self.capabilities

    def to_public(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "capabilities": self.capabilities,
            "modality": self.modality,
            "enabled": self.enabled,
            "default_temperature": self.default_temperature,
            "context": self.context,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- #
# Canonical registry (defaults). Overrides merged from state_store at runtime.
# --------------------------------------------------------------------------- #
_MODELS: Dict[str, ModelSpec] = {
    "nemotron-lightning": ModelSpec(
        "nemotron-lightning", "nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b",
        "Nemotron 3.5 Lightning 30B A3B",
        [Capability.CHAT, Capability.REASONING, Capability.STRUCTURED_OUTPUT],
        Modality.TEXT, default_temperature=0.4, context="long",
        notes="Fast / high-volume bulk generation & enrichment.",
    ),
    "kimi-k3": ModelSpec(
        "kimi-k3", "nvidia", "moonshotai/kimi-k3", "Kimi K3",
        [Capability.CHAT, Capability.REASONING, Capability.VISION,
         Capability.TOOL_CALLING, Capability.LONG_CONTEXT, Capability.STRUCTURED_OUTPUT],
        Modality.MULTIMODAL, default_temperature=0.6, context="long",
        notes="Advanced / agentic / complex reasoning & multimodal.",
    ),
    "gpt-oss-20b": ModelSpec(
        "gpt-oss-20b", "nvidia", "openai/gpt-oss-20b", "GPT-OSS-20B",
        [Capability.CHAT, Capability.REASONING, Capability.TOOL_CALLING,
         Capability.STRUCTURED_OUTPUT],
        Modality.TEXT, default_temperature=0.3,
        notes="Lightweight reasoning / classification / inexpensive fallback. Text-only.",
    ),
    "nemotron-embed": ModelSpec(
        "nemotron-embed", "nvidia", "nvidia/nemotron-3-embed-1b", "Nemotron 3 Embed 1B",
        [Capability.EMBEDDING], Modality.EMBEDDING,
        notes="Embeddings only — semantic search / similarity / RAG.",
    ),
    "riva-translate": ModelSpec(
        "riva-translate", "nvidia", "nvidia/riva-translate-4b-instruct-v2",
        "Riva Translate 4B Instruct v2",
        [Capability.TRANSLATION], Modality.TRANSLATION,
        notes="Dedicated translation capability.",
    ),
    "nemotron-super": ModelSpec(
        "nemotron-super", "nvidia", "nvidia/nemotron-3-super-120b-a12b",
        "Nemotron 3 Super 120B A12B",
        [Capability.CHAT, Capability.REASONING, Capability.LONG_CONTEXT,
         Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT],
        Modality.TEXT, default_temperature=0.5, context="long",
        notes="High-quality / advanced reasoning & final content evaluation.",
    ),
    "muse-glimmer": ModelSpec(
        "muse-glimmer", "nvidia", "meta/muse-glimmer-30b", "Muse Glimmer 30B",
        [Capability.CHAT, Capability.VISION, Capability.REASONING,
         Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT],
        Modality.MULTIMODAL, default_temperature=0.5,
        notes="Multimodal (text + image) vocabulary extraction & visual analysis.",
    ),
    # Existing Emergent Universal LLM / GPT-5.6 Luna — kept as fallback + coach.
    "emergent-luna": ModelSpec(
        "emergent-luna", "emergent", "gpt-5.6-luna", "Emergent Universal (GPT-5.6 Luna)",
        [Capability.CHAT, Capability.REASONING, Capability.VISION,
         Capability.STRUCTURED_OUTPUT],
        Modality.MULTIMODAL,
        notes="Existing provider. Fallback + student AI Coach.",
    ),
}


def all_models() -> List[ModelSpec]:
    return list(_MODELS.values())


def get_model(key: str) -> Optional[ModelSpec]:
    return _MODELS.get(key)


def provider_has_key(provider: str) -> bool:
    if provider == "nvidia":
        return bool(os.environ.get("NVIDIA_API_KEY"))
    if provider == "emergent":
        return bool(os.environ.get("EMERGENT_LLM_KEY"))
    return False


def default_status(spec: ModelSpec) -> str:
    """Status before any override/call is recorded."""
    if not provider_has_key(spec.provider):
        return ModelStatus.UNAVAILABLE   # provider not configured
    return ModelStatus.UNKNOWN


def merge_state(spec: ModelSpec, cfg_models: Dict[str, Any]) -> Dict[str, Any]:
    """Public model view enriched with persisted enable/disable + live status."""
    base = spec.to_public()
    st = cfg_models.get(spec.key, {}) if cfg_models else {}
    enabled = st.get("enabled", spec.enabled)
    base["enabled"] = enabled
    if not provider_has_key(spec.provider):
        base["status"] = ModelStatus.UNAVAILABLE
        base["status_reason"] = "provider API key not configured"
    elif not enabled:
        base["status"] = ModelStatus.DISABLED
        base["status_reason"] = "disabled by admin"
    else:
        base["status"] = st.get("status", ModelStatus.UNKNOWN)
        base["status_reason"] = st.get("last_error", "")
    base["last_success"] = st.get("last_success")
    base["failure_count"] = st.get("failure_count", 0)
    base["last_latency_ms"] = st.get("last_latency_ms")
    return base


def is_enabled(spec: ModelSpec, cfg_models: Dict[str, Any]) -> bool:
    if not provider_has_key(spec.provider):
        return False
    st = cfg_models.get(spec.key, {}) if cfg_models else {}
    return st.get("enabled", spec.enabled)
