from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
