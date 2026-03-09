from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .chunk_models import TS_SYMBOL_CHUNK_STRATEGY
from .content_classification import CODE_CONTEXT_CONTENT_TYPE, CODE_SYMBOL_CONTENT_TYPE

_HEADER_SCAN_MAX_LINES = 12
_CLASS_FIELD_MAX_NAMES = 6
_IDENTIFIER_RE = r"[A-Za-z_$][\w$]*"
_CLASS_DECL_RE = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\b")
_FUNCTION_DECL_RE = re.compile(
    rf"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?P<name>{_IDENTIFIER_RE})\s*(?:<[^{{(]+>\s*)?\("
)
_VARIABLE_DECL_RE = re.compile(
    rf"^(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+(?P<name>{_IDENTIFIER_RE})\b"
)
_CLASS_METHOD_RE = re.compile(
    rf"^(?:(?:public|private|protected|readonly|static|abstract|override|declare|async)\s+)*(?:(?:get|set)\s+)?(?P<name>{_IDENTIFIER_RE})\s*(?:<[^{{(]+>\s*)?\("
)
_CLASS_ARROW_METHOD_RE = re.compile(
    rf"^(?:(?:public|private|protected|readonly|static|abstract|override|declare)\s+)*(?P<name>{_IDENTIFIER_RE})\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|{_IDENTIFIER_RE}\s*=>)"
)
_CLASS_FIELD_RE = re.compile(
    rf"^(?:(?:public|private|protected|readonly|static|declare)\s+)*(?P<name>{_IDENTIFIER_RE})\s*(?::|=)"
)
_IMPORT_FROM_RE = re.compile(r"""from\s+["'](?P<module>[^"']+)["']""")
_IMPORT_SIDE_EFFECT_RE = re.compile(r"""^import\s+["'](?P<module>[^"']+)["']""")
_EXPORT_LIST_RE = re.compile(r"""^export\s*{\s*(?P<body>[^}]+)\s*}""")
_HOOK_NAME_RE = re.compile(r"^use[A-Z0-9_]")
_DEFAULT_WRAPPED_FUNCTION_RE = re.compile(
    rf"^export\s+default\s+.*?function\s+(?P<name>{_IDENTIFIER_RE})\s*(?:<[^{{(]+>\s*)?\("
)
_DEFAULT_ANONYMOUS_FUNCTION_RE = re.compile(r"^export\s+default\s+(?:async\s+)?function\s*\(")


@dataclass(frozen=True, slots=True)
class TsChunkSpec:
    startLine: int
    endLine: int
    content: str
    contentType: str
    chunkStrategy: str = TS_SYMBOL_CHUNK_STRATEGY
    symbolName: str | None = None
    qualifiedSymbolName: str | None = None
    symbolType: str | None = None
    parentSymbol: str | None = None
    signature: str | None = None
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    coveredLineRanges: tuple[tuple[int, int], ...] = field(default_factory=tuple, repr=False)


@dataclass(frozen=True, slots=True)
class _Declaration:
    kind: str
    name: str
    signature: str
    exported: bool
    uses_block: bool


def chunk_ts_source(
    *,
    text: str,
    language: str,
    file_content_type: str,
    class_max_lines: int,
) -> tuple[TsChunkSpec, ...] | None:
    source_lines = text.splitlines()
    sanitized_lines = _sanitize_lines(text)

    if not _has_balanced_structure(sanitized_lines):
        return None

    depth_by_line = _line_start_depths(sanitized_lines)
    if depth_by_line is None:
        return None

    specs, declared_exports = _build_module_chunks(
        source_lines=source_lines,
        sanitized_lines=sanitized_lines,
        depth_by_line=depth_by_line,
        language=language,
        file_content_type=file_content_type,
        class_max_lines=class_max_lines,
    )
    if specs is None:
        return None

    imports = _extract_imports(
        source_lines=source_lines,
        sanitized_lines=sanitized_lines,
        depth_by_line=depth_by_line,
    )
    exports = _collect_exports(
        source_lines=source_lines,
        sanitized_lines=sanitized_lines,
        depth_by_line=depth_by_line,
        declared_exports=declared_exports,
    )
    specs.extend(
        _build_uncovered_source_chunks(
            specs=specs,
            source_lines=source_lines,
            content_type=file_content_type,
        )
    )
    enriched_specs = [
        replace(
            spec,
            imports=imports,
            exports=exports,
        )
        for spec in specs
    ]
    return tuple(
        sorted(
            enriched_specs,
            key=lambda spec: (
                spec.startLine,
                0 if spec.symbolName is not None else 1,
                spec.endLine,
                spec.symbolName or "",
            ),
        )
    )


def _sanitize_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_block_comment = False
    string_quote: str | None = None

    for raw_line in text.splitlines():
        sanitized_chars: list[str] = []
        index = 0

        while index < len(raw_line):
            current = raw_line[index]
            next_char = raw_line[index + 1] if index + 1 < len(raw_line) else ""

            if in_block_comment:
                if current == "*" and next_char == "/":
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if string_quote is not None:
                if current == "\\":
                    index += 2
                    continue
                if current == string_quote:
                    string_quote = None
                index += 1
                continue

            if current == "/" and next_char == "/":
                break
            if current == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
            if current in {"'", '"', "`"}:
                string_quote = current
                index += 1
                continue

            sanitized_chars.append(current)
            index += 1

        lines.append("".join(sanitized_chars))

    return lines


def _has_balanced_structure(sanitized_lines: list[str]) -> bool:
    opening_by_closing = {"}": "{", ")": "(", "]": "["}
    stack: list[str] = []

    for line in sanitized_lines:
        for char in line:
            if char in {"{", "(", "["}:
                stack.append(char)
                continue
            if char in opening_by_closing:
                if not stack or stack[-1] != opening_by_closing[char]:
                    return False
                stack.pop()

    return not stack


def _line_start_depths(sanitized_lines: list[str]) -> list[int] | None:
    depth = 0
    depths: list[int] = []

    for line in sanitized_lines:
        depths.append(depth)
        for char in line:
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth < 0:
                    return None

    if depth != 0:
        return None

    return depths


def _build_module_chunks(
    *,
    source_lines: list[str],
    sanitized_lines: list[str],
    depth_by_line: list[int],
    language: str,
    file_content_type: str,
    class_max_lines: int,
) -> tuple[list[TsChunkSpec], list[str]] | tuple[None, None]:
    chunks: list[TsChunkSpec] = []
    declared_exports: list[str] = []
    line_index = 0

    while line_index < len(source_lines):
        if depth_by_line[line_index] != 0:
            line_index += 1
            continue

        stripped = sanitized_lines[line_index].strip()
        if not stripped:
            line_index += 1
            continue
        if stripped.startswith("import "):
            statement_end = _find_statement_end(
                sanitized_lines=sanitized_lines,
                start_index=line_index,
            )
            if statement_end is None:
                return None, None
            line_index = statement_end + 1
            continue
        if stripped.startswith("export {") or stripped.startswith("export *"):
            statement_end = _find_statement_end(
                sanitized_lines=sanitized_lines,
                start_index=line_index,
            )
            if statement_end is None:
                return None, None
            line_index = statement_end + 1
            continue

        header_end_index, _, header_sanitized = _collect_header(
            source_lines=source_lines,
            sanitized_lines=sanitized_lines,
            start_index=line_index,
        )
        declaration = _match_top_level_declaration(header_sanitized)
        if declaration is None:
            line_index += 1
            continue

        if declaration.exported:
            declared_exports.append(declaration.name)

        if declaration.kind == "class":
            declaration_start_index = _find_decorator_start_index(
                start_index=line_index,
                sanitized_lines=sanitized_lines,
                depth_by_line=depth_by_line,
                expected_depth=0,
            )
            block_end = _find_block_end(
                sanitized_lines=sanitized_lines,
                start_index=line_index,
            )
            if block_end is None:
                return None, None
            class_chunks = _build_class_chunks(
                class_name=declaration.name,
                class_signature=declaration.signature,
                class_declaration_start_index=declaration_start_index,
                class_header_end_index=header_end_index,
                class_start_index=line_index,
                class_end_index=block_end,
                source_lines=source_lines,
                sanitized_lines=sanitized_lines,
                depth_by_line=depth_by_line,
                file_content_type=file_content_type,
                class_max_lines=class_max_lines,
            )
            if class_chunks is None:
                return None, None
            chunks.extend(class_chunks)
            line_index = block_end + 1
            continue

        declaration_end = _find_declaration_end(
            sanitized_lines=sanitized_lines,
            start_index=line_index,
            uses_block=declaration.uses_block,
        )
        if declaration_end is None:
            return None, None

        declaration_start_index = _find_decorator_start_index(
            start_index=line_index,
            sanitized_lines=sanitized_lines,
            depth_by_line=depth_by_line,
            expected_depth=0,
        )
        content = _slice_source(source_lines, declaration_start_index + 1, declaration_end + 1)
        symbol_type = _resolve_top_level_symbol_type(
            language=language,
            name=declaration.name,
            content=content,
            exported=declaration.exported,
        )
        chunks.append(
            TsChunkSpec(
                startLine=declaration_start_index + 1,
                endLine=declaration_end + 1,
                content=content,
                contentType=_resolve_symbol_content_type(file_content_type),
                symbolName=declaration.name,
                qualifiedSymbolName=declaration.name,
                symbolType=symbol_type,
                signature=declaration.signature,
                coveredLineRanges=((declaration_start_index + 1, declaration_end + 1),),
            )
        )
        line_index = declaration_end + 1

    return chunks, declared_exports


def _build_class_chunks(
    *,
    class_name: str,
    class_signature: str,
    class_declaration_start_index: int,
    class_header_end_index: int,
    class_start_index: int,
    class_end_index: int,
    source_lines: list[str],
    sanitized_lines: list[str],
    depth_by_line: list[int],
    file_content_type: str,
    class_max_lines: int,
) -> list[TsChunkSpec] | None:
    content_type = _resolve_symbol_content_type(file_content_type)
    class_span = class_end_index - class_start_index + 1
    method_chunks: list[TsChunkSpec] = []
    method_names: list[str] = []
    line_index = class_start_index + 1

    while line_index < class_end_index:
        if depth_by_line[line_index] != 1:
            line_index += 1
            continue

        stripped = sanitized_lines[line_index].strip()
        if not stripped or stripped in {"}", "};"}:
            line_index += 1
            continue

        _, _, header_sanitized = _collect_header(
            source_lines=source_lines,
            sanitized_lines=sanitized_lines,
            start_index=line_index,
        )
        declaration = _match_class_member_declaration(header_sanitized)
        if declaration is None:
            line_index += 1
            continue

        declaration_start_index = _find_decorator_start_index(
            start_index=line_index,
            sanitized_lines=sanitized_lines,
            depth_by_line=depth_by_line,
            expected_depth=1,
        )
        method_end = _find_declaration_end(
            sanitized_lines=sanitized_lines,
            start_index=line_index,
            uses_block=declaration.uses_block,
        )
        if method_end is None or method_end > class_end_index:
            return None

        qualified_name = f"{class_name}.{declaration.name}"
        method_names.append(declaration.name)
        method_chunks.append(
            TsChunkSpec(
                startLine=declaration_start_index + 1,
                endLine=method_end + 1,
                content=_slice_source(source_lines, declaration_start_index + 1, method_end + 1),
                contentType=content_type,
                symbolName=declaration.name,
                qualifiedSymbolName=qualified_name,
                symbolType="method",
                parentSymbol=class_name,
                signature=declaration.signature,
                coveredLineRanges=((declaration_start_index + 1, method_end + 1),),
            )
        )
        line_index = method_end + 1

    if class_span <= class_max_lines or not method_chunks:
        return [
            TsChunkSpec(
                startLine=class_declaration_start_index + 1,
                endLine=class_end_index + 1,
                content=_slice_source(
                    source_lines,
                    class_declaration_start_index + 1,
                    class_end_index + 1,
                ),
                contentType=content_type,
                symbolName=class_name,
                qualifiedSymbolName=class_name,
                symbolType="class",
                signature=class_signature,
                coveredLineRanges=((class_declaration_start_index + 1, class_end_index + 1),),
            )
        ]

    return [
        TsChunkSpec(
            startLine=class_declaration_start_index + 1,
            endLine=class_end_index + 1,
            content=_build_large_class_summary_content(
                class_signature=class_signature,
                class_name=class_name,
                method_names=method_names,
                decorator_lines=_slice_source(
                    source_lines,
                    class_declaration_start_index + 1,
                    class_start_index,
                ).splitlines(),
                field_names=_extract_class_field_names(
                    source_lines=source_lines,
                    sanitized_lines=sanitized_lines,
                    depth_by_line=depth_by_line,
                    class_start_index=class_start_index,
                    class_end_index=class_end_index,
                ),
            ),
            contentType=content_type,
            symbolName=class_name,
            qualifiedSymbolName=class_name,
            symbolType="class",
            signature=class_signature,
            coveredLineRanges=((class_declaration_start_index + 1, class_header_end_index + 1),),
        ),
        *method_chunks,
    ]


def _build_uncovered_source_chunks(
    *,
    specs: list[TsChunkSpec],
    source_lines: list[str],
    content_type: str,
) -> list[TsChunkSpec]:
    covered_lines = [False] * len(source_lines)

    for spec in specs:
        for start_line, end_line in spec.coveredLineRanges:
            for line_index in range(max(start_line, 1) - 1, min(end_line, len(source_lines))):
                covered_lines[line_index] = True

    chunks: list[TsChunkSpec] = []
    line_index = 0

    while line_index < len(source_lines):
        if covered_lines[line_index]:
            line_index += 1
            continue

        range_start = line_index
        while line_index < len(source_lines) and not covered_lines[line_index]:
            line_index += 1
        range_end = line_index - 1

        useful_indexes = [
            index
            for index in range(range_start, range_end + 1)
            if _is_useful_source_line(source_lines[index])
        ]
        if not useful_indexes:
            continue

        start_line = useful_indexes[0] + 1
        end_line = useful_indexes[-1] + 1
        chunks.append(
            TsChunkSpec(
                startLine=start_line,
                endLine=end_line,
                content=_slice_source(source_lines, start_line, end_line),
                contentType=content_type,
                coveredLineRanges=((start_line, end_line),),
            )
        )

    return chunks


def _extract_imports(
    *,
    source_lines: list[str],
    sanitized_lines: list[str],
    depth_by_line: list[int],
) -> tuple[str, ...]:
    modules: list[str] = []
    line_index = 0

    while line_index < len(source_lines):
        if depth_by_line[line_index] != 0:
            line_index += 1
            continue

        stripped = sanitized_lines[line_index].strip()
        if not stripped.startswith("import "):
            line_index += 1
            continue

        statement_end = _find_statement_end(
            sanitized_lines=sanitized_lines,
            start_index=line_index,
        )
        if statement_end is None:
            break
        statement = _collapse_inline_text(
            " ".join(source_lines[line_index : statement_end + 1])
        )
        module = _extract_import_module(statement)
        if module is not None:
            modules.append(module)
        line_index = statement_end + 1

    return tuple(_unique(modules))


def _collect_exports(
    *,
    source_lines: list[str],
    sanitized_lines: list[str],
    depth_by_line: list[int],
    declared_exports: list[str],
) -> tuple[str, ...]:
    exports = list(declared_exports)
    line_index = 0

    while line_index < len(source_lines):
        if depth_by_line[line_index] != 0:
            line_index += 1
            continue

        stripped = sanitized_lines[line_index].strip()
        if not stripped.startswith("export "):
            line_index += 1
            continue

        statement_end = _find_statement_end(
            sanitized_lines=sanitized_lines,
            start_index=line_index,
        )
        if statement_end is None:
            break
        statement = _collapse_inline_text(
            " ".join(source_lines[line_index : statement_end + 1])
        )
        export_match = _EXPORT_LIST_RE.match(statement)
        if export_match is not None:
            for item in export_match.group("body").split(","):
                normalized = item.strip()
                if not normalized:
                    continue
                if " as " in normalized:
                    normalized = normalized.split(" as ", 1)[1].strip()
                exports.append(normalized)
        else:
            default_export_name = _extract_default_export_name(statement)
            if default_export_name is not None:
                exports.append(default_export_name)
        line_index = statement_end + 1

    return tuple(_unique(exports))


def _collect_header(
    *,
    source_lines: list[str],
    sanitized_lines: list[str],
    start_index: int,
) -> tuple[int, str, str]:
    original_parts: list[str] = []
    sanitized_parts: list[str] = []
    max_index = min(len(source_lines), start_index + _HEADER_SCAN_MAX_LINES)

    for index in range(start_index, max_index):
        original_parts.append(source_lines[index].rstrip())
        sanitized_parts.append(sanitized_lines[index].strip())
        collapsed = _collapse_inline_text(" ".join(part for part in sanitized_parts if part))
        if any(token in collapsed for token in ("{", "=>", ";")):
            return index, "\n".join(original_parts), collapsed
        if index > start_index and not sanitized_lines[index].strip():
            break

    final_index = min(max_index - 1, len(source_lines) - 1)
    return (
        final_index,
        "\n".join(original_parts),
        _collapse_inline_text(" ".join(part for part in sanitized_parts if part)),
    )


def _match_top_level_declaration(header: str) -> _Declaration | None:
    stripped = header.strip()
    exported = stripped.startswith("export ")

    class_name = _extract_class_symbol_name(stripped)
    if class_name is not None:
        return _Declaration(
            kind="class",
            name=class_name,
            signature=_build_signature(stripped),
            exported=exported,
            uses_block=True,
        )

    function_match = _FUNCTION_DECL_RE.match(stripped)
    if function_match is not None:
        uses_block = "{" in stripped
        if not uses_block:
            return None
        return _Declaration(
            kind="function",
            name=function_match.group("name"),
            signature=_build_signature(stripped),
            exported=exported,
            uses_block=uses_block,
        )

    wrapped_function_match = _DEFAULT_WRAPPED_FUNCTION_RE.match(stripped)
    if wrapped_function_match is not None:
        uses_block = "{" in stripped
        if not uses_block:
            return None
        return _Declaration(
            kind="function",
            name=wrapped_function_match.group("name"),
            signature=_build_signature(stripped),
            exported=exported,
            uses_block=uses_block,
        )

    anonymous_default_declaration = _match_anonymous_default_declaration(stripped)
    if anonymous_default_declaration is not None:
        return anonymous_default_declaration

    variable_match = _VARIABLE_DECL_RE.match(stripped)
    if variable_match is None:
        return None
    if "=>" not in stripped and not re.search(r"=\s*(?:async\s+)?function\b", stripped):
        return None

    return _Declaration(
        kind="function",
        name=variable_match.group("name"),
        signature=_build_signature(stripped),
        exported=exported,
        uses_block="{" in stripped or "function" in stripped,
    )


def _match_anonymous_default_declaration(header: str) -> _Declaration | None:
    if not header.startswith("export default "):
        return None
    if _extract_class_symbol_name(header) is not None:
        return None

    normalized = header[len("export default ") :].strip()
    if not normalized:
        return None

    if _DEFAULT_ANONYMOUS_FUNCTION_RE.match(header) is not None:
        uses_block = "{" in header
        if not uses_block:
            return None
        return _Declaration(
            kind="function",
            name="default",
            signature=_build_signature(header),
            exported=True,
            uses_block=True,
        )

    if "=>" not in normalized:
        return None

    return _Declaration(
        kind="function",
        name="default",
        signature=_build_signature(header),
        exported=True,
        uses_block="{" in header or "function" in header,
    )


def _match_class_member_declaration(header: str) -> _Declaration | None:
    stripped = header.strip()

    method_match = _CLASS_METHOD_RE.match(stripped)
    if method_match is not None:
        uses_block = "{" in stripped
        if not uses_block:
            return None
        return _Declaration(
            kind="method",
            name=method_match.group("name"),
            signature=_build_signature(stripped),
            exported=False,
            uses_block=uses_block,
        )

    arrow_method_match = _CLASS_ARROW_METHOD_RE.match(stripped)
    if arrow_method_match is not None:
        return _Declaration(
            kind="method",
            name=arrow_method_match.group("name"),
            signature=_build_signature(stripped),
            exported=False,
            uses_block="{" in stripped or "function" in stripped,
        )

    return None


def _find_declaration_end(
    *,
    sanitized_lines: list[str],
    start_index: int,
    uses_block: bool,
) -> int | None:
    if uses_block:
        return _find_block_end(sanitized_lines=sanitized_lines, start_index=start_index)
    return _find_statement_end(sanitized_lines=sanitized_lines, start_index=start_index)


def _find_block_end(*, sanitized_lines: list[str], start_index: int) -> int | None:
    depth = 0
    saw_open = False

    for line_index in range(start_index, len(sanitized_lines)):
        line = sanitized_lines[line_index]
        for char_index, char in enumerate(line):
            if char == "{":
                depth += 1
                saw_open = True
                continue
            if char == "}":
                if not saw_open:
                    return None
                depth -= 1
                if depth < 0:
                    return None
                if depth == 0:
                    if "{" in line[char_index + 1 :]:
                        continue
                    return line_index

    return None


def _find_statement_end(*, sanitized_lines: list[str], start_index: int) -> int | None:
    paren_depth = 0
    bracket_depth = 0

    for line_index in range(start_index, len(sanitized_lines)):
        line = sanitized_lines[line_index]
        for char in line:
            if char == "(":
                paren_depth += 1
                continue
            if char == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    return None
                continue
            if char == "[":
                bracket_depth += 1
                continue
            if char == "]":
                bracket_depth -= 1
                if bracket_depth < 0:
                    return None
                continue
            if char == ";" and paren_depth == 0 and bracket_depth == 0:
                return line_index

        if (
            line_index > start_index
            and paren_depth == 0
            and bracket_depth == 0
            and line.strip()
            and not line.rstrip().endswith(",")
        ):
            return line_index

    return None


def _resolve_top_level_symbol_type(
    *,
    language: str,
    name: str,
    content: str,
    exported: bool,
) -> str:
    if _HOOK_NAME_RE.match(name):
        return "hook"
    if name == "default" and exported and _looks_like_anonymous_default_component(
        language=language,
        content=content,
    ):
        return "component"
    if _looks_like_component(language=language, name=name, content=content):
        return "component"
    if exported:
        return "helper"
    return "function"


def _looks_like_anonymous_default_component(*, language: str, content: str) -> bool:
    if language not in {"typescriptreact", "javascriptreact"}:
        return False
    return "<" in content and ("/>" in content or "</" in content)


def _looks_like_component(*, language: str, name: str, content: str) -> bool:
    if not name or not name[0].isupper():
        return False
    if language in {"typescriptreact", "javascriptreact"}:
        return True
    return "<" in content and "/>" in content


def _resolve_symbol_content_type(file_content_type: str) -> str:
    if file_content_type == CODE_CONTEXT_CONTENT_TYPE:
        return CODE_SYMBOL_CONTENT_TYPE
    return file_content_type


def _extract_class_field_names(
    *,
    source_lines: list[str],
    sanitized_lines: list[str],
    depth_by_line: list[int],
    class_start_index: int,
    class_end_index: int,
) -> tuple[str, ...]:
    field_names: list[str] = []

    for line_index in range(class_start_index + 1, class_end_index):
        if depth_by_line[line_index] != 1:
            continue
        stripped = sanitized_lines[line_index].strip()
        if not stripped:
            continue
        if _match_class_member_declaration(stripped) is not None:
            continue
        match = _CLASS_FIELD_RE.match(stripped)
        if match is not None:
            field_names.append(match.group("name"))
        if len(field_names) >= _CLASS_FIELD_MAX_NAMES:
            break

    return tuple(field_names)


def _build_large_class_summary_content(
    *,
    class_signature: str,
    class_name: str,
    method_names: list[str],
    decorator_lines: list[str],
    field_names: tuple[str, ...],
) -> str:
    lines = [line for line in decorator_lines if line.strip()]
    lines.append(class_signature)
    if field_names:
        lines.append(f"fields: {', '.join(field_names)}")
    if method_names:
        unique_method_names = _unique(method_names)
        lines.append(f"methods: {', '.join(unique_method_names)}")
    lines.append(f"class_summary: {class_name}")
    return "\n".join(lines)


def _extract_import_module(statement: str) -> str | None:
    match = _IMPORT_FROM_RE.search(statement)
    if match is not None:
        return match.group("module")
    match = _IMPORT_SIDE_EFFECT_RE.match(statement)
    if match is not None:
        return match.group("module")
    return None


def _extract_default_export_name(statement: str) -> str | None:
    if not statement.startswith("export default "):
        return None

    normalized = statement[len("export default ") :].strip()
    if not normalized:
        return None

    named_function_match = re.match(rf"function\s+(?P<name>{_IDENTIFIER_RE})\b", normalized)
    if named_function_match is not None:
        return named_function_match.group("name")

    class_symbol_name = _extract_class_symbol_name(statement)
    if class_symbol_name is not None:
        return class_symbol_name

    wrapped_named_function_match = re.search(
        rf"function\s+(?P<name>{_IDENTIFIER_RE})\b",
        normalized,
    )
    if wrapped_named_function_match is not None:
        return wrapped_named_function_match.group("name")

    if normalized.startswith(("function", "class", "(")) or "=>" in normalized:
        return "default"

    identifier_match = re.match(rf"(?P<name>{_IDENTIFIER_RE})\b", normalized)
    if identifier_match is not None:
        return identifier_match.group("name")

    return "default"


def _build_signature(header: str) -> str:
    collapsed = _collapse_inline_text(header)
    if collapsed.endswith("{"):
        return collapsed[:-1].rstrip()
    return collapsed.rstrip(";")


def _extract_class_symbol_name(header: str) -> str | None:
    stripped = header.strip()
    class_match = _CLASS_DECL_RE.match(stripped)
    if class_match is None:
        return None

    remainder = stripped[class_match.end() :].lstrip()
    if not remainder:
        return "default" if _is_default_export_declaration(stripped) else None

    candidate_match = re.match(rf"(?P<name>{_IDENTIFIER_RE})\b", remainder)
    if candidate_match is None:
        return "default" if _is_default_export_declaration(stripped) else None

    candidate = candidate_match.group("name")
    if candidate in {"extends", "implements"}:
        return "default" if _is_default_export_declaration(stripped) else None

    return candidate


def _is_default_export_declaration(header: str) -> bool:
    return header.startswith("export default ") or header.startswith("export default abstract ")


def _find_decorator_start_index(
    *,
    start_index: int,
    sanitized_lines: list[str],
    depth_by_line: list[int],
    expected_depth: int,
) -> int:
    candidate = start_index
    reverse_paren_balance = 0
    found_decorator = False
    line_index = start_index - 1

    while line_index >= 0:
        if depth_by_line[line_index] < expected_depth:
            break
        previous_line = sanitized_lines[line_index].strip()
        if not previous_line:
            break

        reverse_paren_balance += previous_line.count(")") - previous_line.count("(")

        if previous_line.startswith("@"):
            candidate = line_index
            found_decorator = True
            line_index -= 1
            continue

        if not found_decorator and reverse_paren_balance <= 0:
            break
        if found_decorator and reverse_paren_balance <= 0:
            break

        line_index -= 1

    if not found_decorator:
        return start_index

    return candidate


def _slice_source(source_lines: list[str], start_line: int, end_line: int) -> str:
    return "\n".join(source_lines[start_line - 1 : end_line])


def _collapse_inline_text(value: str) -> str:
    return " ".join(value.strip().split())


def _is_useful_source_line(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    return normalized not in {"{", "}", "};", ";"}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
