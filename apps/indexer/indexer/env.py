from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

DEFAULT_ENV_FILES = (".env", ".env.local")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_search_paths() -> list[Path]:
    return _unique_paths([_repo_root()])


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
        value = value[1:-1]
    return key, value


def _load_env_file(path: Path, keys_from_files: set[str]) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if not parsed:
            continue
        key, value = parsed
        if key in os.environ and key not in keys_from_files:
            continue
        os.environ[key] = value
        keys_from_files.add(key)


def load_env_files(
    search_paths: Iterable[Path] | None = None,
    filenames: Iterable[str] = DEFAULT_ENV_FILES,
) -> list[Path]:
    loaded: list[Path] = []
    keys_from_files: set[str] = set()
    paths = _unique_paths(search_paths) if search_paths is not None else _default_search_paths()

    for base in paths:
        for filename in filenames:
            candidate = base / filename
            if not candidate.is_file():
                continue
            _load_env_file(candidate, keys_from_files)
            loaded.append(candidate)

    return loaded
