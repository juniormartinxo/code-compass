from __future__ import annotations


def chunk_sql_source(text: str) -> tuple[tuple[int, int, str], ...]:
    lines = text.splitlines()
    if not lines:
        return ()

    chunks: list[tuple[int, int, str]] = []
    current_lines: list[str] = []
    current_start_line: int | None = None
    paren_depth = 0
    in_single_quote = False
    in_double_quote = False
    in_block_comment = False
    dollar_quote_tag: str | None = None

    for index, line in enumerate(lines, start=1):
        if current_start_line is None and line.strip():
            current_start_line = index
        if current_start_line is not None:
            current_lines.append(line)

        statement_complete = False
        char_index = 0
        while char_index < len(line):
            current = line[char_index]
            next_char = line[char_index + 1] if char_index + 1 < len(line) else ""

            if in_block_comment:
                if current == "*" and next_char == "/":
                    in_block_comment = False
                    char_index += 2
                    continue
                char_index += 1
                continue

            if dollar_quote_tag is not None:
                if line.startswith(dollar_quote_tag, char_index):
                    closing_tag = dollar_quote_tag
                    dollar_quote_tag = None
                    char_index += len(closing_tag)
                    continue
                char_index += 1
                continue

            if not in_single_quote and not in_double_quote:
                if current == "-" and next_char == "-":
                    break
                if current == "/" and next_char == "*":
                    in_block_comment = True
                    char_index += 2
                    continue
                dollar_tag = _match_dollar_quote_tag(line, char_index)
                if dollar_tag is not None:
                    dollar_quote_tag = dollar_tag
                    char_index += len(dollar_tag)
                    continue

            if current == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                char_index += 1
                continue
            if current == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                char_index += 1
                continue

            if in_single_quote or in_double_quote:
                char_index += 1
                continue

            if current == "(":
                paren_depth += 1
            elif current == ")":
                paren_depth = max(paren_depth - 1, 0)
            elif current == ";" and paren_depth == 0:
                statement_complete = True

            char_index += 1

        if statement_complete and current_start_line is not None:
            chunk = _build_chunk(
                lines=current_lines,
                start_line=current_start_line,
            )
            if chunk is not None:
                chunks.append(chunk)
            current_lines = []
            current_start_line = None

    if current_start_line is not None:
        chunk = _build_chunk(
            lines=current_lines,
            start_line=current_start_line,
        )
        if chunk is not None:
            chunks.append(chunk)

    return tuple(chunks)


def _match_dollar_quote_tag(line: str, char_index: int) -> str | None:
    if line[char_index] != "$":
        return None

    end_index = line.find("$", char_index + 1)
    if end_index == -1:
        return None

    tag = line[char_index : end_index + 1]
    inner_tag = tag[1:-1]
    if not inner_tag:
        return "$$"
    if inner_tag[0].isdigit():
        return None
    if not all(char.isalnum() or char == "_" for char in inner_tag):
        return None
    return tag


def _build_chunk(
    *,
    lines: list[str],
    start_line: int,
) -> tuple[int, int, str] | None:
    start_offset = 0
    end_offset = len(lines) - 1

    while start_offset <= end_offset and not lines[start_offset].strip():
        start_offset += 1
    while end_offset >= start_offset and not lines[end_offset].strip():
        end_offset -= 1

    if start_offset > end_offset:
        return None

    return (
        start_line + start_offset,
        start_line + end_offset,
        "\n".join(lines[start_offset : end_offset + 1]),
    )
