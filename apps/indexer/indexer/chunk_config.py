from __future__ import annotations

import re
from pathlib import Path

_SECTION_HEADER_RE = re.compile(r"^\s*\[\[?[^\]]+\]\]\s*$")


def chunk_config_source(
    *,
    text: str,
    path: Path,
) -> tuple[tuple[int, int, str], ...]:
    lines = text.splitlines()
    if not lines:
        return ()

    file_name = path.name.lower()
    suffix = path.suffix.lower()

    if file_name == ".env":
        blocks = _split_env_blocks(lines)
    elif suffix in {".ini", ".cfg", ".conf", ".toml"}:
        blocks = _split_by_indexes(lines, _find_section_indexes(lines))
    elif suffix in {".yaml", ".yml"}:
        blocks = _split_by_indexes(lines, _find_yaml_block_indexes(lines))
    elif suffix == ".json":
        blocks = _split_by_indexes(lines, _find_json_block_indexes(lines))
    else:
        blocks = []

    if blocks:
        return tuple(blocks)

    chunk = _build_chunk(lines=lines, start_index=0, end_index=len(lines) - 1)
    return (chunk,) if chunk is not None else ()


def _find_section_indexes(lines: list[str]) -> list[int]:
    return [
        index
        for index, line in enumerate(lines)
        if _SECTION_HEADER_RE.match(line)
    ]


def _find_yaml_block_indexes(lines: list[str]) -> list[int]:
    indexes: list[int] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[:1].isspace() or stripped.startswith("-"):
            continue
        if ":" not in stripped:
            continue
        indexes.append(index)
    return indexes


def _find_json_block_indexes(lines: list[str]) -> list[int]:
    indexes: list[int] = []
    brace_depth = 0
    bracket_depth = 0
    string_quote: str | None = None
    escaped = False

    for index, line in enumerate(lines):
        line_start_brace_depth = brace_depth
        line_start_bracket_depth = bracket_depth

        for char in line:
            if string_quote is not None:
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == string_quote:
                    string_quote = None
                continue

            if char in {'"', "'"}:
                string_quote = char
                continue
            if char == "{":
                brace_depth += 1
                continue
            if char == "}":
                brace_depth = max(brace_depth - 1, 0)
                continue
            if char == "[":
                bracket_depth += 1
                continue
            if char == "]":
                bracket_depth = max(bracket_depth - 1, 0)

        stripped = line.strip()
        if (
            line_start_brace_depth == 1
            and line_start_bracket_depth == 0
            and stripped.startswith('"')
            and ":" in stripped
        ):
            indexes.append(index)

    return indexes


def _split_env_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    block_start: int | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if block_start is not None:
                chunk = _build_chunk(
                    lines=lines,
                    start_index=block_start,
                    end_index=index - 1,
                )
                if chunk is not None:
                    chunks.append(chunk)
                block_start = None
            continue
        if block_start is None:
            block_start = index

    if block_start is not None:
        chunk = _build_chunk(
            lines=lines,
            start_index=block_start,
            end_index=len(lines) - 1,
        )
        if chunk is not None:
            chunks.append(chunk)

    return chunks


def _split_by_indexes(
    lines: list[str],
    indexes: list[int],
) -> list[tuple[int, int, str]]:
    if not indexes:
        return []

    chunks: list[tuple[int, int, str]] = []
    if indexes[0] > 0:
        preamble = _build_chunk(
            lines=lines,
            start_index=0,
            end_index=indexes[0] - 1,
        )
        if preamble is not None:
            chunks.append(preamble)

    for offset, start_index in enumerate(indexes):
        next_index = indexes[offset + 1] if offset + 1 < len(indexes) else len(lines)
        chunk = _build_chunk(
            lines=lines,
            start_index=start_index,
            end_index=next_index - 1,
        )
        if chunk is not None:
            chunks.append(chunk)

    return chunks


def _build_chunk(
    *,
    lines: list[str],
    start_index: int,
    end_index: int,
) -> tuple[int, int, str] | None:
    while start_index <= end_index and not lines[start_index].strip():
        start_index += 1
    while end_index >= start_index and not lines[end_index].strip():
        end_index -= 1

    if start_index > end_index:
        return None

    return (
        start_index + 1,
        end_index + 1,
        "\n".join(lines[start_index : end_index + 1]),
    )
