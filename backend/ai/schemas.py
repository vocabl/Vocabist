"""Enums, constants and Pydantic I/O schemas for the AI Gateway."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Capabilities / modality / status (string enums kept as plain constants)
# --------------------------------------------------------------------------- #
class Capability:
    CHAT = "chat"
    REASONING = "reasoning"
    VISION = "vision"
    EMBEDDING = "embedding"
    TRANSLATION = "translation"
    TOOL_CALLING = "tool_calling"
    LONG_CONTEXT = "long_context"
    STRUCTURED_OUTPUT = "structured_output"


class Modality:
    TEXT = "text"
    MULTIMODAL = "multimodal"
    EMBEDDING = "embedding"
    TRANSLATION = "translation"


class ModelStatus:
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
class Task:
    VOCABULARY_GENERATION = "vocabulary_generation"
    VOCABULARY_ENRICHMENT = "vocabulary_enrichment"
    ADVANCED_VOCABULARY_ANALYSIS = "advanced_vocabulary_analysis"
    PRACTICE_GENERATION = "practice_generation"
    CLASSIFICATION = "classification"
    SEMANTIC_EMBEDDING = "semantic_embedding"
    TRANSLATION = "translation"
    MULTIMODAL_LEARNING = "multimodal_learning"
    LONG_DOCUMENT_ANALYSIS = "long_document_analysis"
    ADVANCED_AGENTIC_TASK = "advanced_agentic_task"
    AI_COACH_ADVANCED = "ai_coach_advanced"
    AI_COACH = "ai_coach"  # existing student word-coach (behavior preserved)


ALL_TASKS: List[str] = [
    Task.VOCABULARY_GENERATION,
    Task.VOCABULARY_ENRICHMENT,
    Task.ADVANCED_VOCABULARY_ANALYSIS,
    Task.PRACTICE_GENERATION,
    Task.CLASSIFICATION,
    Task.SEMANTIC_EMBEDDING,
    Task.TRANSLATION,
    Task.MULTIMODAL_LEARNING,
    Task.LONG_DOCUMENT_ANALYSIS,
    Task.ADVANCED_AGENTIC_TASK,
    Task.AI_COACH_ADVANCED,
    Task.AI_COACH,
]

# Capability a model MUST have to serve a given task.
TASK_REQUIRED_CAPABILITY: Dict[str, str] = {
    Task.VOCABULARY_GENERATION: Capability.CHAT,
    Task.VOCABULARY_ENRICHMENT: Capability.CHAT,
    Task.ADVANCED_VOCABULARY_ANALYSIS: Capability.CHAT,
    Task.PRACTICE_GENERATION: Capability.CHAT,
    Task.CLASSIFICATION: Capability.CHAT,
    Task.SEMANTIC_EMBEDDING: Capability.EMBEDDING,
    Task.TRANSLATION: Capability.TRANSLATION,
    Task.MULTIMODAL_LEARNING: Capability.VISION,
    Task.LONG_DOCUMENT_ANALYSIS: Capability.CHAT,
    Task.ADVANCED_AGENTIC_TASK: Capability.CHAT,
    Task.AI_COACH_ADVANCED: Capability.CHAT,
    Task.AI_COACH: Capability.CHAT,
}


# --------------------------------------------------------------------------- #
# Job statuses
# --------------------------------------------------------------------------- #
class JobStatus:
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# --------------------------------------------------------------------------- #
# Admin API request bodies
# --------------------------------------------------------------------------- #
class RoutingUpdateBody(BaseModel):
    task: str
    chain: List[str] = Field(default_factory=list)  # ordered model keys
    enabled: bool = True


class ModelToggleBody(BaseModel):
    enabled: bool


class GenerateBody(BaseModel):
    count: int = Field(default=10, ge=1, le=200)
    cefr: Optional[str] = None
    topic: Optional[str] = None
    part_of_speech: Optional[str] = None
    exam: Optional[str] = None
    vocabulary_type: Optional[str] = None       # e.g. academic / everyday / idioms
    model: Optional[str] = None                  # force a specific model key (Auto if None)
    enrichment_level: str = "standard"           # minimal | standard | rich


class RegenerateFieldBody(BaseModel):
    field: str                                   # definition | examples | synonyms | antonyms | cefr | word_family | memory_hook | common_mistake
    model: Optional[str] = None


class TranslateBody(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str
    model: Optional[str] = None


class RejectBody(BaseModel):
    reason: Optional[str] = None
