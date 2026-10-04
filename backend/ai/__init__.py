"""Vocabist AI Gateway package.

Centralized AI infrastructure for Vocabist:

    Feature → Gateway → Task Router → Provider → Model → Structured Result → Validation → Feature

No student-facing feature or admin feature should call NVIDIA (or any provider)
directly — everything flows through ``ai.gateway``.
"""
from .gateway import gateway  # noqa: F401
