from __future__ import annotations

import re

def chunk_by_paragraph(text: str, max_size: int = 300) -> list[str]:
    if not text:
        return []
    if max_size <= 0:
        return [text]
    if len(text) <= max_size:
        return [text]

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(paragraph, max_size=max_size))
            continue

        if not current:
            current = paragraph
            continue

        candidate = f"{current}{paragraph}"
        if len(candidate) > max_size:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    # Keep `\n\n...` separators interleaved so joining chunks reproduces input exactly.
    # `re.split` with a capture group returns separators as odd-indexed entries.
    parts = re.split(r"(\n\n+)", text)
    if len(parts) == 1:
        return [text]

    paragraphs: list[str] = []
    index = 0
    total = len(parts)

    while index < total:
        piece = parts[index]
        separator = parts[index + 1] if index + 1 < total else ""
        combined = f"{piece}{separator}"
        if combined:
            paragraphs.append(combined)
        index += 2

    return paragraphs


def _split_long_paragraph(paragraph: str, *, max_size: int) -> list[str]:
    if len(paragraph) <= max_size:
        return [paragraph]

    lines = paragraph.splitlines(keepends=True)
    if not lines:
        return _split_long_text(paragraph, max_size=max_size)

    chunks: list[str] = []
    current = ""
    for line in lines:
        if len(line) > max_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(line, max_size=max_size))
            continue

        # Defensive invariant: oversized lines are handled in the branch above.
        assert len(line) <= max_size
        candidate = f"{current}{line}"
        if len(candidate) > max_size and current:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def _split_long_text(text: str, *, max_size: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + max_size])
        start += max_size
    return chunks
