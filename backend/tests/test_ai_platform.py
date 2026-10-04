"""Unit tests for the Vocabist AI Gateway platform (no network).

Covers: model registry, capability validation, task routing + fallback ordering,
structured JSON extraction, normalized error fallback flags, usage aggregation,
and admin email allowlist parsing.
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from ai import registry, router
from ai.schemas import Task, Capability, TASK_REQUIRED_CAPABILITY, ALL_TASKS
from ai.gateway import extract_json
from ai.errors import (
    TimeoutError_, RateLimited, ProviderServerError, MalformedOutput,
    ModelUnavailable, AuthError, BadRequest, ConfigurationError,
)


def test_all_seven_nvidia_models_plus_emergent_registered():
    keys = {m.key for m in registry.all_models()}
    expected = {
        "nemotron-lightning", "kimi-k3", "gpt-oss-20b", "nemotron-embed",
        "riva-translate", "nemotron-super", "muse-glimmer", "emergent-luna",
    }
    assert expected.issubset(keys)
    # canonical NVIDIA model IDs
    assert registry.get_model("nemotron-lightning").model_id == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert registry.get_model("kimi-k3").model_id == "moonshotai/kimi-k3"
    assert registry.get_model("gpt-oss-20b").model_id == "openai/gpt-oss-20b"
    assert registry.get_model("nemotron-embed").model_id == "nvidia/nemotron-3-embed-1b"
    assert registry.get_model("riva-translate").model_id == "nvidia/riva-translate-4b-instruct-v2"
    assert registry.get_model("nemotron-super").model_id == "nvidia/nemotron-3-super-120b-a12b"
    assert registry.get_model("muse-glimmer").model_id == "meta/muse-glimmer-30b"


def test_capabilities_and_modality():
    assert registry.get_model("nemotron-embed").capabilities == [Capability.EMBEDDING]
    assert Capability.TRANSLATION in registry.get_model("riva-translate").capabilities
    assert Capability.VISION in registry.get_model("muse-glimmer").capabilities
    assert Capability.VISION in registry.get_model("kimi-k3").capabilities
    # GPT-OSS is text-only (no vision)
    assert Capability.VISION not in registry.get_model("gpt-oss-20b").capabilities


def test_routing_capability_validation():
    # embedding task must use an embedding-capable model
    assert router.capability_valid(Task.SEMANTIC_EMBEDDING, "nemotron-embed")
    assert not router.capability_valid(Task.SEMANTIC_EMBEDDING, "nemotron-lightning")
    # translation task requires translation capability
    assert router.capability_valid(Task.TRANSLATION, "riva-translate")
    assert not router.capability_valid(Task.TRANSLATION, "gpt-oss-20b")
    # multimodal requires vision
    assert router.capability_valid(Task.MULTIMODAL_LEARNING, "muse-glimmer")
    assert not router.capability_valid(Task.MULTIMODAL_LEARNING, "gpt-oss-20b")


def test_resolve_chain_drops_incapable_and_respects_order():
    cfg = {"models": {}, "routing": {}}
    chain = router.resolve_chain(Task.VOCABULARY_GENERATION, cfg)
    keys = [s.key for s in chain]
    # nemotron-lightning should be primary, emergent fallback last
    assert keys[0] == "nemotron-lightning"
    assert "emergent-luna" in keys
    # embedding model must never appear in a chat task
    assert "nemotron-embed" not in keys


def test_disabled_model_excluded_from_chain():
    cfg = {"models": {"nemotron-lightning": {"enabled": False}}, "routing": {}}
    chain = router.resolve_chain(Task.VOCABULARY_GENERATION, cfg)
    assert "nemotron-lightning" not in [s.key for s in chain]


def test_prefer_model_moves_to_front():
    cfg = {"models": {}, "routing": {}}
    chain = router.resolve_chain(Task.VOCABULARY_GENERATION, cfg, prefer_model="nemotron-super")
    assert chain[0].key == "nemotron-super"


def test_routing_view_covers_all_tasks():
    view = router.routing_view({"models": {}, "routing": {}})
    assert len(view) == len(ALL_TASKS)
    for r in view:
        assert r["required_capability"] == TASK_REQUIRED_CAPABILITY[r["task"]]


def test_error_fallback_flags():
    assert TimeoutError_().fallbackable is True
    assert RateLimited().fallbackable is True
    assert ProviderServerError().fallbackable is True
    assert MalformedOutput().fallbackable is True
    assert ModelUnavailable().fallbackable is True
    # non-fallbackable: auth / bad request
    assert AuthError().fallbackable is False
    assert BadRequest().fallbackable is False
    assert ConfigurationError().fallbackable is False


def test_extract_json_handles_fences_and_prose():
    assert extract_json('{"a":1}') == {"a": 1}
    assert extract_json('```json\n{"a":2}\n```') == {"a": 2}
    assert extract_json('here you go: {"words":[{"headword":"x"}]} thanks')["words"][0]["headword"] == "x"
    assert extract_json('[1,2,3]') == [1, 2, 3]
    try:
        extract_json("no json here")
        assert False, "should have raised"
    except MalformedOutput:
        pass


def test_usage_aggregate_shape():
    from ai import usage
    agg = asyncio.get_event_loop().run_until_complete(usage.aggregate())
    for key in ("requests_total", "success_rate", "fallback_rate", "by_model", "token_info"):
        assert key in agg
    # token/cost never faked
    assert agg["estimated_cost"] == "Unavailable"


def test_admin_email_allowlist_parsing():
    from admin_routes import _admin_emails
    os.environ["ADMIN_EMAILS"] = "A@B.com, c@d.com"
    emails = _admin_emails()
    assert "a@b.com" in emails and "c@d.com" in emails


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
