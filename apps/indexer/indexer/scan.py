from __future__ import annotations

import fnmatch
import logging
import os
import re
from pathlib import Path
from time import perf_counter

logger = logging.getLogger(__name__)


def _is_binary_file(path: Path, sample_size: int = 4096) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(sample_size)
    except OSError:
        return True

    if not chunk:
        return False

    if b"\x00" in chunk:
        return True

    return False


def _compile_ignore_patterns(patterns: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Pré-compila globs para regex (fnmatch.translate). Executado uma única vez."""
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for pattern in patterns:
        try:
            regex = re.compile(fnmatch.translate(pattern))
            compiled.append((pattern, regex))
        except re.error:
            logger.warning(f"Padrão de ignore inválido (ignorado): '{pattern}'")
    return compiled


def _matches_ignore_pattern(
    rel_path: str,
    compiled_patterns: list[tuple[str, re.Pattern[str]]],
) -> str | None:
    """Verifica se o path relativo corresponde a algum padrão. Retorna o padrão ou None."""
    for pattern, regex in compiled_patterns:
        if regex.match(rel_path):
            return pattern
    return None


def scan_repo(
    repo_root: Path,
    ignore_dirs: set[str],
    allow_exts: set[str],
    max_files: int | None = None,
    ignore_patterns: list[str] | None = None,
) -> tuple[list[Path], dict[str, int]]:
    started = perf_counter()

    # Pré-compilar padrões de ignore uma única vez
    compiled_patterns = _compile_ignore_patterns(ignore_patterns or [])
    if compiled_patterns:
        logger.info(
            f"Ignore patterns ativos ({len(compiled_patterns)}): "
            f"{[p for p, _ in compiled_patterns]}"
        )

    stats: dict[str, int] = {
        "total_files_seen": 0,
        "total_dirs_seen": 0,
        "files_kept": 0,
        "files_ignored_ext": 0,
        "files_ignored_pattern": 0,
        "files_ignored_binary": 0,
        "dirs_ignored": 0,
        "elapsed_ms": 0,
    }

    files: list[Path] = []
    stack: list[Path] = [repo_root]

    while stack:
        current_dir = stack.pop()

        try:
            with os.scandir(current_dir) as entries:
                stats["total_dirs_seen"] += 1

                for entry in entries:
                    entry_name = entry.name

                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        is_file = entry.is_file(follow_symlinks=False)
                    except OSError:
                        continue

                    # 1. Diretórios ignorados (Set lookup - O(1))
                    if is_dir:
                        if entry_name in ignore_dirs:
                            stats["dirs_ignored"] += 1
                            logger.debug(f"Pulando diretório: {entry_name} (ignore_dirs)")
                            continue
                        stack.append(Path(entry.path))
                        continue

                    if not is_file:
                        continue

                    stats["total_files_seen"] += 1

                    # 2. Whitelist de extensões (Set lookup - O(1)) — falha rápida
                    suffix = Path(entry_name).suffix.lower()
                    if not suffix or suffix not in allow_exts:
                        stats["files_ignored_ext"] += 1
                        logger.debug(
                            f"Pulando {entry_name}: extensão '{suffix}' não está em allow_exts"
                        )
                        continue

                    # 3. Blacklist de padrões (Regex pré-compilado)
                    file_path = Path(entry.path)
                    relative = file_path.relative_to(repo_root)
                    rel_posix = relative.as_posix()

                    if compiled_patterns:
                        matched_pattern = _matches_ignore_pattern(rel_posix, compiled_patterns)
                        if matched_pattern is not None:
                            stats["files_ignored_pattern"] += 1
                            logger.debug(
                                f"Pulando {rel_posix}: corresponde a ignore_pattern "
                                f"'{matched_pattern}'"
                            )
                            continue

                    # 4. Verificação de binário (I/O) — último recurso
                    if _is_binary_file(file_path):
                        stats["files_ignored_binary"] += 1
                        logger.debug(f"Pulando {rel_posix}: arquivo binário")
                        continue

                    files.append(Path(rel_posix))
                    stats["files_kept"] += 1
        except OSError:
            continue

    files.sort(key=lambda item: item.as_posix())

    stats["elapsed_ms"] = int((perf_counter() - started) * 1000)

    if max_files is not None and max_files >= 0:
        return files[:max_files], stats

    return files, stats
