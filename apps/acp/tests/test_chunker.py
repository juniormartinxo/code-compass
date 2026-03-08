from __future__ import annotations

import pytest

from code_compass_acp.chunker import chunk_by_paragraph


def test_chunker_returns_empty_for_empty_text() -> None:
    assert chunk_by_paragraph("") == []


def test_chunker_preserves_original_text_with_paragraphs() -> None:
    text = "Primeiro paragrafo.\n\nSegundo paragrafo.\n\nTerceiro."
    chunks = chunk_by_paragraph(text, max_size=12)
    assert chunks
    assert "".join(chunks) == text


def test_chunker_preserves_markdown_code_fences() -> None:
    text = (
        "## Titulo\n\n"
        "Texto inicial.\n\n"
        "```typescript\n"
        "const x = 1;\n"
        "\n"
        "function test() {\n"
        "  return x;\n"
        "}\n"
        "```\n\n"
        "## Fim\n"
        "- item 1\n"
        "- item 2\n"
    )
    chunks = chunk_by_paragraph(text, max_size=40)
    assert chunks
    assert "".join(chunks) == text


def test_chunker_respects_max_size_for_non_empty_chunks() -> None:
    text = "linha-1\n\nlinha-2 muito longa para forcar mais de um chunk\n\nlinha-3"
    chunks = chunk_by_paragraph(text, max_size=20)
    assert chunks
    assert all(0 < len(chunk) <= 20 for chunk in chunks)


@pytest.mark.parametrize("max_size", [0, -1])
def test_chunker_returns_original_text_when_max_size_is_non_positive(max_size: int) -> None:
    text = "texto curto"
    assert chunk_by_paragraph(text, max_size=max_size) == [text]


def test_chunker_splits_text_without_paragraph_separator() -> None:
    text = "linha-1\nlinha-2-maior\nlinha-3"
    chunks = chunk_by_paragraph(text, max_size=8)
    assert chunks
    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= 8 for chunk in chunks)


def test_chunker_discards_whitespace_only_text() -> None:
    assert chunk_by_paragraph("   \n\n\t  ", max_size=3) == []


def test_split_paragraphs_discards_whitespace_only_segments() -> None:
    text = "   \n\n\t\t\n\nconteudo util\n\n   "

    assert chunk_by_paragraph(text, max_size=20) == ["conteudo util\n\n"]


def test_split_long_paragraph_preserves_size_invariant() -> None:
    paragraph = "a\nb\nc\n"

    chunks = chunk_by_paragraph(paragraph, max_size=4)

    assert chunks
    assert "".join(chunks) == paragraph
    assert all(0 < len(chunk) <= 4 for chunk in chunks)
