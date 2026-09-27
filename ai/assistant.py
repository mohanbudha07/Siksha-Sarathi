"""Compatibility wrapper for the grounded student AI tutor."""

from ai.grounded_tutor import (
    DEFAULT_MODEL,
    MAX_ANSWER_LENGTH,
    SYSTEM_INSTRUCTION,
    generate_answer,
    generate_fallback_answer,
    get_subject,
)

__all__ = [
    "DEFAULT_MODEL",
    "MAX_ANSWER_LENGTH",
    "SYSTEM_INSTRUCTION",
    "generate_answer",
    "generate_fallback_answer",
    "get_subject",
]
