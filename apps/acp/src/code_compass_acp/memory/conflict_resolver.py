from __future__ import annotations

import os
import re
from enum import StrEnum

from .env_utils import env_float


class ConflictResolution(StrEnum):
    REINFORCEMENT = "reinforcement"
    COMPLEMENT = "complement"
    CONTRADICTION = "contradiction"
    INDEPENDENT = "independent"


def memory_similarity_thresholds() -> tuple[float, float]:
    mode = os.getenv("ACP_MEMORY_SIMILARITY_MODE", "").strip().lower() or "lexical"
    if mode == "semantic":
        default_high = 0.92
        default_medium = 0.78
    else:
        # Fallback lexical (Jaccard), com thresholds mais realistas.
        default_high = 0.60
        default_medium = 0.30
    high = env_float("ACP_MEMORY_SIMILARITY_HIGH", default_high)
    medium = env_float("ACP_MEMORY_SIMILARITY_MEDIUM", default_medium)
    if medium > high:
        medium = high
    return high, medium


def classify_conflict(
    *,
    existing_value: str,
    new_value: str,
    similarity: float,
    high_threshold: float | None = None,
    medium_threshold: float | None = None,
) -> ConflictResolution:
    high, medium = memory_similarity_thresholds()
    high = high_threshold if high_threshold is not None else high
    medium = medium_threshold if medium_threshold is not None else medium

    if similarity >= high:
        if _looks_contradictory(existing_value, new_value):
            return ConflictResolution.CONTRADICTION
        return ConflictResolution.REINFORCEMENT
    if similarity >= medium:
        return ConflictResolution.COMPLEMENT
    return ConflictResolution.INDEPENDENT


def lexical_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(intersection) / len(union)


def _tokenize(value: str) -> set[str]:
    tokens = re.split(r"[^a-zA-Z0-9_]+", value.lower())
    return {token for token in tokens if token}


def _looks_contradictory(existing_value: str, new_value: str) -> bool:
    left_neg = _contains_negation(existing_value)
    right_neg = _contains_negation(new_value)
    if left_neg == right_neg:
        return False
    overlap = _tokenize(existing_value) & _tokenize(new_value)
    return len(overlap) >= 2


def _contains_negation(value: str) -> bool:
    normalized = f" {value.lower()} "
    markers = [
        " nao ",
        " não ",
        " never ",
        " not ",
        " dont ",
        " don't ",
        " sem ",
    ]
    return any(marker in normalized for marker in markers)
