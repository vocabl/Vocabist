"""Task-based model routing + capability-validated fallback chains.

Routing is configurable (persisted overrides in state_store). Feature routes
never hard-code model choices — they ask the gateway for a task.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import registry
from .schemas import Task, TASK_REQUIRED_CAPABILITY, ALL_TASKS

# Default routing: ordered list of model keys (primary → fallbacks).
DEFAULT_ROUTING: Dict[str, List[str]] = {
    Task.VOCABULARY_GENERATION: ["nemotron-lightning", "gpt-oss-20b", "nemotron-super", "emergent-luna"],
    Task.VOCABULARY_ENRICHMENT: ["nemotron-lightning", "nemotron-super", "kimi-k3", "emergent-luna"],
    Task.ADVANCED_VOCABULARY_ANALYSIS: ["nemotron-super", "kimi-k3", "emergent-luna"],
    Task.PRACTICE_GENERATION: ["nemotron-lightning", "gpt-oss-20b", "nemotron-super", "emergent-luna"],
    Task.CLASSIFICATION: ["gpt-oss-20b", "nemotron-lightning", "emergent-luna"],
    Task.SEMANTIC_EMBEDDING: ["nemotron-embed"],
    Task.TRANSLATION: ["riva-translate", "emergent-luna"],
    Task.MULTIMODAL_LEARNING: ["muse-glimmer", "kimi-k3", "emergent-luna"],
    Task.LONG_DOCUMENT_ANALYSIS: ["nemotron-super", "kimi-k3", "emergent-luna"],
    Task.ADVANCED_AGENTIC_TASK: ["kimi-k3", "nemotron-super", "emergent-luna"],
    Task.AI_COACH_ADVANCED: ["nemotron-super", "kimi-k3", "emergent-luna"],
    # Existing student word coach: Emergent primary to preserve current behavior.
    Task.AI_COACH: ["emergent-luna", "nemotron-super"],
}


def configured_chain(task: str, cfg: Dict[str, Any]) -> List[str]:
    """Raw configured chain (override → default), before capability/enable filtering."""
    routing = (cfg or {}).get("routing", {})
    entry = routing.get(task)
    if entry and entry.get("enabled", True) and entry.get("chain"):
        return list(entry["chain"])
    return list(DEFAULT_ROUTING.get(task, []))


def resolve_chain(
    task: str,
    cfg: Dict[str, Any],
    prefer_model: Optional[str] = None,
) -> List[registry.ModelSpec]:
    """Return the ordered, capability-valid, enabled ModelSpec chain for a task.

    - A forced ``prefer_model`` is moved to the front (if capable).
    - Models lacking the task's required capability are dropped.
    - Disabled models / providers without keys are dropped.
    """
    required = TASK_REQUIRED_CAPABILITY.get(task, "chat")
    cfg_models = (cfg or {}).get("models", {})
    keys = configured_chain(task, cfg)

    if prefer_model and prefer_model in keys:
        keys = [prefer_model] + [k for k in keys if k != prefer_model]
    elif prefer_model:
        keys = [prefer_model] + keys

    chain: List[registry.ModelSpec] = []
    seen = set()
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        spec = registry.get_model(k)
        if not spec:
            continue
        if not spec.has(required):
            continue
        if not registry.is_enabled(spec, cfg_models):
            continue
        chain.append(spec)
    return chain


def capability_valid(task: str, model_key: str) -> bool:
    required = TASK_REQUIRED_CAPABILITY.get(task, "chat")
    spec = registry.get_model(model_key)
    return bool(spec and spec.has(required))


def routing_view(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Admin view of all task routes (effective chain + validity)."""
    out: List[Dict[str, Any]] = []
    for task in ALL_TASKS:
        chain = configured_chain(task, cfg)
        routing = (cfg or {}).get("routing", {})
        entry = routing.get(task, {})
        out.append({
            "task": task,
            "required_capability": TASK_REQUIRED_CAPABILITY.get(task),
            "chain": chain,
            "enabled": entry.get("enabled", True),
            "is_override": bool(entry.get("chain")),
            "invalid_models": [k for k in chain if not capability_valid(task, k)],
        })
    return out
