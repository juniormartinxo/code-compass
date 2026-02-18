from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_IGNORE_DIRS: set[str] = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".qdrant_storage",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

DEFAULT_ALLOW_EXTS: set[str] = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
}

DEFAULT_IGNORE_PATTERNS: list[str] = []

DEFAULT_CHUNK_LINES = 120
DEFAULT_CHUNK_OVERLAP_LINES = 20

DEFAULT_EXCLUDED_CONTEXT_PATH_PARTS: tuple[str, ...] = (
    "/.venv/",
    "/venv/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/.mypy_cache/",
    "/.ruff_cache/",
)
DEFAULT_SEARCH_SNIPPET_MAX_CHARS = 300
DEFAULT_DOC_EXTENSIONS: set[str] = {".md", ".mdx", ".rst", ".adoc", ".txt"}
DEFAULT_DOC_PATH_HINTS: tuple[str, ...] = (
    "/docs/",
    "/documentation/",
    "/adr",
    "/wiki/",
    "/changelog",
    "/contributing",
    "/license",
    "/readme",
)
DEFAULT_CONTENT_TYPES: tuple[str, str] = ("code", "docs")
DEFAULT_MIN_FILE_COVERAGE = 0.95


@dataclass(frozen=True)
class ScanConfig:
    repo_root: Path
    ignore_dirs: set[str]
    allow_exts: set[str]
    ignore_patterns: list[str]


@dataclass(frozen=True)
class ChunkConfig:
    repo_root: Path
    chunk_lines: int
    overlap_lines: int


@dataclass(frozen=True)
class RuntimeConfig:
    excluded_context_path_parts: tuple[str, ...]
    search_snippet_max_chars: int
    doc_extensions: set[str]
    doc_path_hints: tuple[str, ...]
    content_types: tuple[str, str]
    min_file_coverage: float


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_ignore_dirs(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        name = Path(value.strip()).name.strip()
        if name:
            normalized.add(name)
    return normalized


def _normalize_allow_exts(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        item = value.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        normalized.add(item)
    return normalized


def _normalize_ignore_patterns(values: Iterable[str]) -> list[str]:
    """Normaliza padrões de ignore (globs). Remove espaços e entradas vazias."""
    patterns: list[str] = []
    for value in values:
        item = value.strip()
        if item:
            patterns.append(item)
    return patterns


def _resolve_repo_root(raw: str | None) -> Path:
    target = Path(raw).expanduser() if raw else Path("..")
    if not target.is_absolute():
        target = Path.cwd() / target
    return target.resolve()


def _resolve_int_config(
    value: int | str | None,
    env_value: str | None,
    default: int,
    label: str,
) -> int:
    selected: int | str
    if value is not None:
        selected = value
    elif env_value is not None:
        selected = env_value
    else:
        selected = default

    try:
        return int(selected)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} deve ser um inteiro válido") from exc


def _parse_positive_int(value: str | None, *, default: int, minimum: int = 1) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed < minimum:
        return default
    return parsed


def _parse_min_file_coverage(value: str | None, *, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    if parsed > 1:
        return 1.0
    return parsed


def _normalize_path_markers(
    values: Iterable[str],
    *,
    ensure_trailing_slash: bool,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        marker = value.strip().replace("\\", "/").lower()
        if not marker:
            continue
        if not marker.startswith("/"):
            marker = f"/{marker}"
        if ensure_trailing_slash and not marker.endswith("/"):
            marker = f"{marker}/"
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(marker)

    return tuple(normalized)


def _resolve_doc_extensions(raw_values: list[str]) -> set[str]:
    if not raw_values:
        return set(DEFAULT_DOC_EXTENSIONS)

    normalized = _normalize_allow_exts(raw_values)
    if not normalized:
        return set(DEFAULT_DOC_EXTENSIONS)
    return normalized


def _resolve_content_types(raw_values: list[str]) -> tuple[str, str]:
    if not raw_values:
        return DEFAULT_CONTENT_TYPES

    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        item = value.strip().lower()
        if item not in {"code", "docs"}:
            continue
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)

    if len(normalized) != 2 or set(normalized) != {"code", "docs"}:
        return DEFAULT_CONTENT_TYPES

    return normalized[0], normalized[1]


def load_scan_config(
    repo_root: str | None = None,
    ignore_dirs: str | Iterable[str] | None = None,
    allow_exts: str | Iterable[str] | None = None,
    ignore_patterns: str | Iterable[str] | None = None,
) -> ScanConfig:
    repo_root_raw = repo_root if repo_root is not None else os.getenv("REPO_ROOT")

    # --- ignore_dirs ---
    env_ignore_dirs = os.getenv("SCAN_IGNORE_DIRS")
    if ignore_dirs is None:
        extra_ignore_dirs = _parse_csv(env_ignore_dirs)
    elif isinstance(ignore_dirs, str):
        extra_ignore_dirs = _parse_csv(ignore_dirs)
    else:
        extra_ignore_dirs = list(ignore_dirs)

    # --- allow_exts ---
    env_allow_exts = os.getenv("SCAN_ALLOW_EXTS")
    if allow_exts is None:
        allow_raw = _parse_csv(env_allow_exts)
    elif isinstance(allow_exts, str):
        allow_raw = _parse_csv(allow_exts)
    else:
        allow_raw = list(allow_exts)

    # --- ignore_patterns (CLI > Env > Default) ---
    env_ignore_patterns = os.getenv("SCAN_IGNORE_PATTERNS")
    if ignore_patterns is not None:
        # CLI tem prioridade máxima
        if isinstance(ignore_patterns, str):
            patterns_raw = _parse_csv(ignore_patterns)
        else:
            patterns_raw = list(ignore_patterns)
    elif env_ignore_patterns:
        # Env tem prioridade secundária
        patterns_raw = _parse_csv(env_ignore_patterns)
    else:
        # Default
        patterns_raw = list(DEFAULT_IGNORE_PATTERNS)

    resolved_ignore_dirs = DEFAULT_IGNORE_DIRS | _normalize_ignore_dirs(extra_ignore_dirs)
    resolved_allow_exts = _normalize_allow_exts(allow_raw) if allow_raw else set(DEFAULT_ALLOW_EXTS)
    resolved_ignore_patterns = _normalize_ignore_patterns(patterns_raw)

    return ScanConfig(
        repo_root=_resolve_repo_root(repo_root_raw),
        ignore_dirs=resolved_ignore_dirs,
        allow_exts=resolved_allow_exts,
        ignore_patterns=resolved_ignore_patterns,
    )


def load_chunk_config(
    repo_root: str | None = None,
    chunk_lines: int | str | None = None,
    overlap_lines: int | str | None = None,
) -> ChunkConfig:
    repo_root_raw = repo_root if repo_root is not None else os.getenv("REPO_ROOT")
    chunk_lines_value = _resolve_int_config(
        value=chunk_lines,
        env_value=os.getenv("CHUNK_LINES"),
        default=DEFAULT_CHUNK_LINES,
        label="CHUNK_LINES",
    )
    overlap_lines_value = _resolve_int_config(
        value=overlap_lines,
        env_value=os.getenv("CHUNK_OVERLAP_LINES"),
        default=DEFAULT_CHUNK_OVERLAP_LINES,
        label="CHUNK_OVERLAP_LINES",
    )

    return ChunkConfig(
        repo_root=_resolve_repo_root(repo_root_raw),
        chunk_lines=chunk_lines_value,
        overlap_lines=overlap_lines_value,
    )


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    source = os.environ if env is None else env

    excluded_raw = _parse_csv(source.get("EXCLUDED_CONTEXT_PATH_PARTS"))
    excluded_context_path_parts = (
        _normalize_path_markers(excluded_raw, ensure_trailing_slash=True)
        if excluded_raw
        else DEFAULT_EXCLUDED_CONTEXT_PATH_PARTS
    )
    if not excluded_context_path_parts:
        excluded_context_path_parts = DEFAULT_EXCLUDED_CONTEXT_PATH_PARTS

    doc_extensions = _resolve_doc_extensions(_parse_csv(source.get("DOC_EXTENSIONS")))

    doc_path_hints_raw = _parse_csv(source.get("DOC_PATH_HINTS"))
    doc_path_hints = (
        _normalize_path_markers(doc_path_hints_raw, ensure_trailing_slash=False)
        if doc_path_hints_raw
        else DEFAULT_DOC_PATH_HINTS
    )
    if not doc_path_hints:
        doc_path_hints = DEFAULT_DOC_PATH_HINTS

    return RuntimeConfig(
        excluded_context_path_parts=excluded_context_path_parts,
        search_snippet_max_chars=_parse_positive_int(
            source.get("SEARCH_SNIPPET_MAX_CHARS"),
            default=DEFAULT_SEARCH_SNIPPET_MAX_CHARS,
            minimum=4,
        ),
        doc_extensions=doc_extensions,
        doc_path_hints=doc_path_hints,
        content_types=_resolve_content_types(_parse_csv(source.get("CONTENT_TYPES"))),
        min_file_coverage=_parse_min_file_coverage(
            source.get("INDEX_MIN_FILE_COVERAGE"),
            default=DEFAULT_MIN_FILE_COVERAGE,
        ),
    )
