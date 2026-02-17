from __future__ import annotations


def chunk_by_paragraph(text: str, max_size: int = 300) -> list[str]:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text] if text else []

    chunks: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= max_size:
            chunks.append(paragraph)
            continue

        lines = [line for line in paragraph.split("\n") if line]
        if len(paragraph) <= max_size or not lines:
            chunks.append(paragraph)
            continue

        current = ""
        for line in lines:
            if not current:
                current = line
                continue

            candidate = f"{current}\n{line}"
            if len(candidate) > max_size:
                chunks.append(current)
                current = line
            else:
                current = candidate

        if current:
            chunks.append(current)

    return _split_long_chunks(chunks, max_size=max_size)


def _split_long_chunks(chunks: list[str], max_size: int) -> list[str]:
    output: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_size:
            output.append(chunk)
            continue

        start = 0
        while start < len(chunk):
            output.append(chunk[start : start + max_size])
            start += max_size
    return output
