from __future__ import annotations

import re

_ATX_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def chunk_markdown_source(text: str) -> tuple[tuple[int, int, str], ...]:
    lines = text.splitlines()
    if not lines:
        return ()

    heading_indexes = _find_heading_indexes(lines)
    if not heading_indexes:
        chunk = _build_chunk(lines=lines, start_index=0, end_index=len(lines) - 1)
        return (chunk,) if chunk is not None else ()

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


def _find_heading_indexes(lines: list[str]) -> list[int]:
    heading_indexes: list[int] = []
    fence_marker: str | None = None
    fence_length = 0

    for index, line in enumerate(lines):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_marker is None:
                fence_marker = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_marker and len(marker) >= fence_length:
                fence_marker = None
                fence_length = 0
            continue

        if fence_marker is not None:
            continue

        if _ATX_HEADING_RE.match(line):
            heading_indexes.append(index)

    return heading_indexes


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
