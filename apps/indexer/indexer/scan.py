from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter


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


def scan_repo(
    repo_root: Path,
    ignore_dirs: set[str],
    allow_exts: set[str],
    max_files: int | None = None,
) -> tuple[list[Path], dict[str, int]]:
    started = perf_counter()

    stats: dict[str, int] = {
        "total_files_seen": 0,
        "total_dirs_seen": 0,
        "files_kept": 0,
        "files_ignored_ext": 0,
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

                    if is_dir:
                        if entry_name in ignore_dirs:
                            stats["dirs_ignored"] += 1
                            continue
                        stack.append(Path(entry.path))
                        continue

                    if not is_file:
                        continue

                    stats["total_files_seen"] += 1
                    suffix = Path(entry_name).suffix.lower()
                    if not suffix or suffix not in allow_exts:
                        stats["files_ignored_ext"] += 1
                        continue

                    file_path = Path(entry.path)
                    if _is_binary_file(file_path):
                        stats["files_ignored_binary"] += 1
                        continue

                    relative = file_path.relative_to(repo_root)
                    files.append(Path(relative.as_posix()))
                    stats["files_kept"] += 1
        except OSError:
            continue

    files.sort(key=lambda item: item.as_posix())

    stats["elapsed_ms"] = int((perf_counter() - started) * 1000)

    if max_files is not None and max_files >= 0:
        return files[:max_files], stats

    return files, stats
