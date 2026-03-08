from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Iterable

from .env_utils import env_float


class MemoryKind(StrEnum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    CONVENTION = "convention"


class MemoryTopic(StrEnum):
    NAME = "name"
    LANGUAGE_PREFERENCE = "language_preference"
    FRAMEWORK_PREFERENCE = "framework_preference"
    STATE_MANAGEMENT_PREFERENCE = "state_management_preference"
    NAMING_CONVENTION = "naming_convention"
    TESTING_CONVENTION = "testing_convention"
    DEVELOPMENT_CONVENTION = "development_convention"


class MemoryStance(StrEnum):
    IDENTITY = "identity"
    PREFER = "prefer"
    AVOID = "avoid"
    REQUIRE = "require"


@dataclass(frozen=True)
class ExtractedMemory:
    kind: str
    topic: str
    value: str
    confidence: float
    stance: str
    source_excerpt: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class PatternSpec:
    name: str
    pattern: re.Pattern[str]
    builder: Callable[[re.Match[str]], ExtractedMemory]


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_MAX_INPUT_CHARS = 500
_MAX_CAPTURE_CHARS = 120

# Confidences heurísticos calibráveis.
# Mantidos centralizados para facilitar ajuste fino posterior com golden set.
_CONFIDENCE_PROFILE = 0.95
_CONFIDENCE_PREFERENCE_LANGUAGE = 0.80
_CONFIDENCE_PREFERENCE_FRAMEWORK = 0.79
_CONFIDENCE_PREFERENCE_STATE = 0.78
_CONFIDENCE_CONVENTION_NAMING = 0.76
_CONFIDENCE_CONVENTION_TESTING = 0.76
_CONFIDENCE_CONVENTION_GENERAL = 0.74

_HEDGING_MARKERS = (
    " mas ",
    " porém ",
    " however ",
    " but ",
    " depends ",
    " depende ",
    " às vezes ",
    " as vezes ",
    " sometimes ",
    " talvez ",
    " maybe ",
    " geralmente ",
    " usually ",
    " acho que ",
    " i think ",
    " talvez eu ",
    " maybe i ",
    " pode ser ",
    " might ",
)

_ALIAS_MAP = {
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "react js": "React",
    "reactjs": "React",
    "nestjs": "NestJS",
    "nextjs": "Next.js",
    "vitest": "Vitest",
    "jest": "Jest",
    "rtl": "React Testing Library",
    "react testing library": "React Testing Library",
    "zustand": "Zustand",
    "redux toolkit": "Redux Toolkit",
    "redux": "Redux",
    "context api": "Context API",
    "context": "Context",
    "camelcase": "camelCase",
    "pascalcase": "PascalCase",
    "snake_case": "snake_case",
    "kebab-case": "kebab-case",
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def _canonical_key(text: str) -> str:
    text = _normalize_whitespace(text).casefold()
    text = _strip_accents(text)
    return text


def _canonicalize_value(value: str) -> str:
    value = _normalize_whitespace(value).strip(" .,:;-'\"()[]{}")
    if not value:
        return value

    key = _canonical_key(value)
    aliased = _ALIAS_MAP.get(key)
    if aliased:
        return aliased

    if value.upper() in {"API", "SQL", "JWT", "REST", "TDD"}:
        return value.upper()

    return value


def _contains_hedging(value: str) -> bool:
    lowered = f" {_strip_accents(value.casefold())} "
    return any(marker in lowered for marker in _HEDGING_MARKERS)


def _is_reasonable_value(value: str) -> bool:
    if not value:
        return False

    normalized = _normalize_whitespace(value)
    if len(normalized) > _MAX_CAPTURE_CHARS:
        return False

    if _contains_hedging(normalized):
        return False

    if normalized.count(",") >= 2:
        return False

    return True


def _source_excerpt(match: re.Match[str], max_len: int = 160) -> str:
    excerpt = _normalize_whitespace(match.group(0))
    if len(excerpt) <= max_len:
        return excerpt
    return excerpt[: max_len - 1] + "…"


def _safe_group(match: re.Match[str], group_name: str) -> str:
    value = match.group(group_name)
    return _canonicalize_value(value)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _build_name_memory(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "name")
    return ExtractedMemory(
        kind=MemoryKind.PROFILE,
        topic=MemoryTopic.NAME,
        value=value,
        confidence=_CONFIDENCE_PROFILE,
        stance=MemoryStance.IDENTITY,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


def _build_language_preference(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "value")
    verb = _canonical_key(match.group("verb"))
    stance = MemoryStance.AVOID if verb in {"odeio", "detesto", "i hate"} else MemoryStance.PREFER

    return ExtractedMemory(
        kind=MemoryKind.PREFERENCE,
        topic=MemoryTopic.LANGUAGE_PREFERENCE,
        value=value,
        confidence=_CONFIDENCE_PREFERENCE_LANGUAGE,
        stance=stance,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


def _build_framework_preference(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "value")
    verb = _canonical_key(match.group("verb"))
    stance = (
        MemoryStance.AVOID
        if verb in {"odeio", "detesto", "não gosto de", "nao gosto de", "i hate", "i dislike"}
        else MemoryStance.PREFER
    )

    return ExtractedMemory(
        kind=MemoryKind.PREFERENCE,
        topic=MemoryTopic.FRAMEWORK_PREFERENCE,
        value=value,
        confidence=_CONFIDENCE_PREFERENCE_FRAMEWORK,
        stance=stance,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


def _build_state_preference(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "value")
    verb = _canonical_key(match.group("verb"))
    stance = MemoryStance.AVOID if verb in {"odeio", "detesto", "i hate"} else MemoryStance.PREFER

    return ExtractedMemory(
        kind=MemoryKind.PREFERENCE,
        topic=MemoryTopic.STATE_MANAGEMENT_PREFERENCE,
        value=value,
        confidence=_CONFIDENCE_PREFERENCE_STATE,
        stance=stance,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


def _build_naming_convention(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "value")
    return ExtractedMemory(
        kind=MemoryKind.CONVENTION,
        topic=MemoryTopic.NAMING_CONVENTION,
        value=value,
        confidence=_CONFIDENCE_CONVENTION_NAMING,
        stance=MemoryStance.REQUIRE,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


def _build_testing_convention(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "value")
    return ExtractedMemory(
        kind=MemoryKind.CONVENTION,
        topic=MemoryTopic.TESTING_CONVENTION,
        value=value,
        confidence=_CONFIDENCE_CONVENTION_TESTING,
        stance=MemoryStance.REQUIRE,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


def _build_general_convention(match: re.Match[str]) -> ExtractedMemory:
    value = _safe_group(match, "value")
    return ExtractedMemory(
        kind=MemoryKind.CONVENTION,
        topic=MemoryTopic.DEVELOPMENT_CONVENTION,
        value=value,
        confidence=_CONFIDENCE_CONVENTION_GENERAL,
        stance=MemoryStance.AVOID,
        source_excerpt=_source_excerpt(match),
        source_start=match.start(),
        source_end=match.end(),
    )


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PATTERN_SPECS: tuple[PatternSpec, ...] = (
    PatternSpec(
        name="name_identity",
        pattern=re.compile(
            r"\b(?:meu nome e|meu nome é|my name is)\s+(?P<name>[A-Za-zÀ-ÿ0-9_\- ]{2,80})\b",
            re.I,
        ),
        builder=_build_name_memory,
    ),
    PatternSpec(
        name="language_preference",
        pattern=re.compile(
            r"\b(?P<verb>prefiro|odeio|detesto|i prefer|i hate)\s+"
            r"(?P<value>[^.!?,]{1,80})"
            r"(?=\s+(?:como linguagem|para linguagem|as a language|for language)|$)",
            re.I,
        ),
        builder=_build_language_preference,
    ),
    PatternSpec(
        name="framework_preference",
        pattern=re.compile(
            r"\b(?P<verb>prefiro|odeio|detesto|gosto de|não gosto de|nao gosto de|i prefer|i hate|i love|i dislike)\s+"
            r"(?P<value>[^.!?,]{1,80})"
            r"(?=\s+(?:framework|library|lib|para api|for api|ao inves de|ao invés de|instead of)|$)",
            re.I,
        ),
        builder=_build_framework_preference,
    ),
    PatternSpec(
        name="state_management_preference",
        pattern=re.compile(
            r"\b(?P<verb>prefiro|odeio|detesto|i prefer|i hate)\s+"
            r"(?P<value>[^.!?,]{1,80})"
            r"(?=\s+(?:para estado|for state|state management)|$)",
            re.I,
        ),
        builder=_build_state_preference,
    ),
    PatternSpec(
        name="state_management_direct",
        pattern=re.compile(
            r"\b(?P<verb>prefiro|odeio|detesto|i prefer|i hate)\s+"
            r"(?P<value>redux toolkit|redux|zustand|context api|context)\b",
            re.I,
        ),
        builder=_build_state_preference,
    ),
    PatternSpec(
        name="naming_convention",
        pattern=re.compile(
            r"\b(?:use sempre|sempre uso|always use|i always use)\s+"
            r"(?P<value>camelcase|camelCase|pascalcase|PascalCase|snake_case|kebab-case|[^.!?,]{1,60})"
            r"(?=\s+(?:para nome|para nomear|for naming|nos nomes|in names)|$)",
            re.I,
        ),
        builder=_build_naming_convention,
    ),
    PatternSpec(
        name="testing_convention",
        pattern=re.compile(
            r"\b(?:uso|use|i use|i prefer)\s+"
            r"(?P<value>vitest|jest|pytest|rtl|react testing library|[^.!?,]{1,60})"
            r"(?=\s+(?:para teste|para testes|for tests|for testing)|$)",
            re.I,
        ),
        builder=_build_testing_convention,
    ),
    PatternSpec(
        name="general_convention",
        pattern=re.compile(
            r"\b(?:nunca use|não use|nao use|never use|do not use|avoid)\s+"
            r"(?P<value>[^.!?]{1,80})$",
            re.I,
        ),
        builder=_build_general_convention,
    ),
)


class MemoryExtractor:
    """
    Extrator conservador de memórias de longo prazo.

    Características desta versão:
    - ignora `assistant_text` deliberadamente por segurança;
    - usa heurísticas léxicas configuráveis, não inferência semântica profunda;
    - suporta múltiplas memórias em um único texto via `finditer`;
    - produz evidência mínima auditável (`source_excerpt`, offsets);
    - deduplica candidatos localmente por semântica superficial;
    - deixa conflito semântico e reconciliação para camadas superiores;
    - usa aliases/canonicalização leve para reduzir variações triviais de valor.

    Limitações conhecidas:
    - cobertura de i18n parcial (pt-BR + en);
    - listas compostas como "redux e zustand" ainda são tratadas como um único valor bruto;
    - o limite de entrada é conservador e baseado em caracteres, não em tokens nem palavras;
    - não há classificação semântica profunda nesta camada.
    """

    def __init__(self, min_confidence: float | None = None) -> None:
        self._min_confidence = (
            min_confidence
            if min_confidence is not None
            else env_float("ACP_MEMORY_MIN_CONFIDENCE", 0.7)
        )

    def extract(self, *, user_text: str, assistant_text: str = "") -> list[ExtractedMemory]:
        _ = assistant_text  # ignorado deliberadamente nesta versão

        normalized = _normalize_whitespace(user_text)
        if not normalized:
            return []

        if len(normalized) > _MAX_INPUT_CHARS:
            return []

        matches = list(self._iter_candidates(normalized))
        matches = self._dedupe(matches)
        matches = self._remove_overlaps(matches)

        return [m for m in matches if m.confidence >= self._min_confidence]

    def _iter_candidates(self, text: str) -> Iterable[ExtractedMemory]:
        for spec in _PATTERN_SPECS:
            for hit in spec.pattern.finditer(text):
                candidate = spec.builder(hit)
                if not _is_reasonable_value(candidate.value):
                    continue
                yield candidate

    def _dedupe(self, items: Iterable[ExtractedMemory]) -> list[ExtractedMemory]:
        best_by_key: dict[tuple[str, str, str, str], ExtractedMemory] = {}

        for item in items:
            key = (
                item.kind,
                item.topic,
                item.stance,
                _canonical_key(item.value),
            )
            current = best_by_key.get(key)
            if current is None or item.confidence > current.confidence:
                best_by_key[key] = item

        return list(best_by_key.values())

    def _remove_overlaps(self, items: list[ExtractedMemory]) -> list[ExtractedMemory]:
        """
        Segunda linha de defesa após `_dedupe`.

        Objetivo:
        - evitar múltiplos matches sobre o mesmo trecho textual quando patterns
          diferentes capturam essencialmente a mesma região.

        Não é resolvedor semântico de conflito.
        A camada superior (`MemoryService` / `ConflictResolver`) continua sendo
        responsável por decidir reforço, complemento e contradição.
        """
        if not items:
            return []

        items_sorted = sorted(
            items,
            key=lambda x: (x.source_start, -(x.source_end - x.source_start), -int(x.confidence * 100)),
        )

        selected: list[ExtractedMemory] = []
        occupied: list[tuple[int, int]] = []

        for item in items_sorted:
            if any(not (item.source_end <= start or item.source_start >= end) for start, end in occupied):
                continue
            selected.append(item)
            occupied.append((item.source_start, item.source_end))

        return sorted(selected, key=lambda x: (x.source_start, x.source_end))
