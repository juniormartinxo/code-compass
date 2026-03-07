from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .env_utils import env_float


@dataclass(frozen=True)
class ExtractedMemory:
    kind: str
    topic: str
    value: str
    confidence: float


class MemoryExtractor:
    """
    Extrator conservador: só registra fatos/preferências com valor provável de longo prazo.
    """

    def __init__(self, min_confidence: float | None = None) -> None:
        self._min_confidence = min_confidence or env_float("ACP_MEMORY_MIN_CONFIDENCE", 0.7)

    def extract(self, *, user_text: str, assistant_text: str = "") -> list[ExtractedMemory]:
        _ = assistant_text  # reservado para heurísticas futuras
        normalized = user_text.strip()
        if not normalized:
            return []
        if len(normalized) > 500:
            return []

        matches: list[ExtractedMemory] = []
        for pattern, builder in _PATTERNS:
            hit = pattern.search(normalized)
            if hit is None:
                continue
            candidate = builder(hit)
            if candidate.confidence >= self._min_confidence:
                matches.append(candidate)
        return matches


def _normalize_capture(value: str) -> str:
    return " ".join(value.strip().split())


def _build_name_memory(match: re.Match[str]) -> ExtractedMemory:
    value = _normalize_capture(match.group("name"))
    return ExtractedMemory(kind="profile", topic="name", value=value, confidence=0.95)


def _build_preference_memory(match: re.Match[str]) -> ExtractedMemory:
    value = _normalize_capture(match.group("value"))
    return ExtractedMemory(kind="preference", topic="technical_preference", value=value, confidence=0.78)


def _build_convention_memory(match: re.Match[str]) -> ExtractedMemory:
    value = _normalize_capture(match.group("value"))
    return ExtractedMemory(kind="convention", topic="development_convention", value=value, confidence=0.74)


_PATTERNS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], ExtractedMemory]], ...] = (
    (
        re.compile(r"\b(?:meu nome e|meu nome é|my name is)\s+(?P<name>[A-Za-z0-9_\- ]{2,80})\b", re.I),
        _build_name_memory,
    ),
    (
        re.compile(r"\b(?:prefiro|i prefer)\s+(?P<value>.+)$", re.I),
        _build_preference_memory,
    ),
    (
        re.compile(r"\b(?:sempre use|always use|nao use|não use|do not use)\s+(?P<value>.+)$", re.I),
        _build_convention_memory,
    ),
)
