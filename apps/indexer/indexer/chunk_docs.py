from __future__ import annotations

import re
from pathlib import Path

from .chunk_markdown import chunk_markdown_source

_ADOC_HEADING_RE = re.compile(r"^\s*={1,6}\s+\S")
_RST_DECORATION_CHARS = set("=-~`:#\"'^_*+<>")


def chunk_docs_source(
    *,
    text: str,
    path: Path,
) -> tuple[tuple[int, int, str], ...]:
    suffix = path.suffix.lower()

    if suffix in {".md", ".mdx"}:
        return chunk_markdown_source(text)
    if suffix == ".rst":
        chunks = _chunk_rst_source(text)
        return chunks or _single_chunk(text)
    if suffix == ".adoc":
        chunks = _chunk_adoc_source(text)
        return chunks or _single_chunk(text)

    return chunk_markdown_source(text)


def _chunk_rst_source(text: str) -> tuple[tuple[int, int, str], ...]:
    lines = text.splitlines()
    if not lines:
        return ()

    heading_indexes = _find_rst_heading_indexes(lines)
    return _split_by_heading_indexes(lines, heading_indexes)


def _chunk_adoc_source(text: str) -> tuple[tuple[int, int, str], ...]:
    lines = text.splitlines()
    if not lines:
        return ()

    heading_indexes = [
        index
        for index, line in enumerate(lines)
        if _ADOC_HEADING_RE.match(line)
    ]
    return _split_by_heading_indexes(lines, heading_indexes)


def _find_rst_heading_indexes(lines: list[str]) -> list[int]:
    indexes: list[int] = []

    for index in range(len(lines) - 1):
        title = lines[index].strip()
        underline = lines[index + 1].strip()
        if not title or not _is_rst_underline(underline):
            continue
        if len(underline) < len(title):
            continue
        indexes.append(index)

    return indexes


def _is_rst_underline(line: str) -> bool:
    if len(line) < 3:
        return False
    marker = line[0]
    return marker in _RST_DECORATION_CHARS and all(char == marker for char in line)


def _single_chunk(text: str) -> tuple[tuple[int, int, str], ...]:
    lines = text.splitlines()
    if not lines:
        return ()

    chunk = _build_chunk(lines=lines, start_index=0, end_index=len(lines) - 1)
    return (chunk,) if chunk is not None else ()


def _split_by_heading_indexes(
    lines: list[str],
    heading_indexes: list[int],
) -> tuple[tuple[int, int, str], ...]:
    if not heading_indexes:
        return ()

    chunks: list[tuple[int, int, str]] = []
    if heading_indexes[0] > 0:
        intro_chunk = _build_chunk(
            lines=lines,
            start_index=0,
            end_index=heading_indexes[0] - 1,
        )
        if intro_chunk is not None:
            chunks.append(intro_chunk)

    for offset, start_index in enumerate(heading_indexes):
        next_heading_index = (
            heading_indexes[offset + 1]
            if offset + 1 < len(heading_indexes)
            else len(lines)
        )
        chunk = _build_chunk(
            lines=lines,
            start_index=start_index,
            end_index=next_heading_index - 1,
        )
        if chunk is not None:
            chunks.append(chunk)

    return tuple(chunks)


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
