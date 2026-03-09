from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .chunk_models import PYTHON_SYMBOL_CHUNK_STRATEGY
from .content_classification import CODE_CONTEXT_CONTENT_TYPE, CODE_SYMBOL_CONTENT_TYPE

_FUNCTION_NODE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_SYMBOL_NODE_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_DOCSTRING_MAX_CHARS = 160


@dataclass(frozen=True, slots=True)
class PythonChunkSpec:
    startLine: int
    endLine: int
    content: str
    contentType: str
    chunkStrategy: str = PYTHON_SYMBOL_CHUNK_STRATEGY
    symbolName: str | None = None
    qualifiedSymbolName: str | None = None
    symbolType: str | None = None
    parentSymbol: str | None = None
    signature: str | None = None
    coveredLineRanges: tuple[tuple[int, int], ...] = field(default_factory=tuple, repr=False)


def chunk_python_source(
    *,
    text: str,
    file_content_type: str,
    class_max_lines: int,
) -> tuple[PythonChunkSpec, ...] | None:
    try:
        module = ast.parse(text)
    except SyntaxError:
        return None

    source_lines = text.splitlines()
    specs = _build_scope_chunks(
        nodes=module.body,
        source_lines=source_lines,
        file_content_type=file_content_type,
        class_max_lines=class_max_lines,
        parent_qualified_name=None,
        include_context_chunks=True,
    )
    specs.extend(
        _build_uncovered_source_chunks(
            specs=specs,
            source_lines=source_lines,
            content_type=file_content_type,
        )
    )
    return tuple(
        sorted(
            specs,
            key=lambda spec: (
                spec.startLine,
                0 if spec.symbolName is not None else 1,
                spec.endLine,
                spec.symbolName or "",
            ),
        )
    )


def _build_scope_chunks(
    *,
    nodes: list[ast.stmt],
    source_lines: list[str],
    file_content_type: str,
    class_max_lines: int,
    parent_qualified_name: str | None,
    include_context_chunks: bool,
) -> list[PythonChunkSpec]:
    chunks: list[PythonChunkSpec] = []
    pending_context_nodes: list[ast.stmt] = []

    for node in nodes:
        if isinstance(node, ast.ClassDef):
            if include_context_chunks and pending_context_nodes:
                chunks.extend(
                    _build_context_chunks(
                        nodes=pending_context_nodes,
                        source_lines=source_lines,
                        content_type=file_content_type,
                    )
                )
                pending_context_nodes = []
            chunks.extend(
                _build_class_chunks(
                    node=node,
                    source_lines=source_lines,
                    file_content_type=file_content_type,
                    class_max_lines=class_max_lines,
                    parent_qualified_name=parent_qualified_name,
                )
            )
            continue

        if isinstance(node, _FUNCTION_NODE_TYPES):
            if include_context_chunks and pending_context_nodes:
                chunks.extend(
                    _build_context_chunks(
                        nodes=pending_context_nodes,
                        source_lines=source_lines,
                        content_type=file_content_type,
                    )
                )
                pending_context_nodes = []
            chunks.append(
                _build_function_chunk(
                    node=node,
                    source_lines=source_lines,
                    file_content_type=file_content_type,
                    parent_qualified_name=parent_qualified_name,
                )
            )
            continue

        if include_context_chunks:
            pending_context_nodes.append(node)

    if include_context_chunks and pending_context_nodes:
        chunks.extend(
            _build_context_chunks(
                nodes=pending_context_nodes,
                source_lines=source_lines,
                content_type=file_content_type,
            )
        )

    return chunks


def _build_context_chunks(
    *,
    nodes: list[ast.stmt],
    source_lines: list[str],
    content_type: str,
) -> list[PythonChunkSpec]:
    ranges: list[tuple[int, int]] = []

    for node in nodes:
        start_line, end_line = _node_span(node)
        if not ranges:
            ranges.append((start_line, end_line))
            continue

        previous_start, previous_end = ranges[-1]
        if start_line <= previous_end + 1:
            ranges[-1] = (previous_start, max(previous_end, end_line))
            continue

        ranges.append((start_line, end_line))

    chunks: list[PythonChunkSpec] = []
    for start_line, end_line in ranges:
        content = _slice_source(source_lines, start_line, end_line)
        if not content.strip():
            continue
        chunks.append(
            PythonChunkSpec(
                startLine=start_line,
                endLine=end_line,
                content=content,
                contentType=content_type,
                coveredLineRanges=((start_line, end_line),),
            )
        )
    return chunks


def _build_function_chunk(
    *,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
    file_content_type: str,
    parent_qualified_name: str | None,
) -> PythonChunkSpec:
    start_line, end_line = _node_span(node)
    symbol_name = node.name
    qualified_symbol_name = _qualify_symbol(parent_qualified_name, symbol_name)
    symbol_type = "method" if parent_qualified_name is not None else "function"
    content_type = _resolve_symbol_content_type(file_content_type)

    return PythonChunkSpec(
        startLine=start_line,
        endLine=end_line,
        content=_slice_source(source_lines, start_line, end_line),
        contentType=content_type,
        symbolName=symbol_name,
        qualifiedSymbolName=qualified_symbol_name,
        symbolType=symbol_type,
        parentSymbol=parent_qualified_name,
        signature=_build_signature(node=node, source_lines=source_lines),
        coveredLineRanges=((start_line, end_line),),
    )


def _build_class_chunks(
    *,
    node: ast.ClassDef,
    source_lines: list[str],
    file_content_type: str,
    class_max_lines: int,
    parent_qualified_name: str | None,
) -> list[PythonChunkSpec]:
    start_line, end_line = _node_span(node)
    qualified_symbol_name = _qualify_symbol(parent_qualified_name, node.name)
    child_symbols = [child for child in node.body if isinstance(child, _SYMBOL_NODE_TYPES)]
    class_span = end_line - start_line + 1
    content_type = _resolve_symbol_content_type(file_content_type)
    signature = _build_signature(node=node, source_lines=source_lines)

    if class_span <= class_max_lines or not child_symbols:
        return [
            PythonChunkSpec(
                startLine=start_line,
                endLine=end_line,
                content=_slice_source(source_lines, start_line, end_line),
                contentType=content_type,
                symbolName=node.name,
                qualifiedSymbolName=qualified_symbol_name,
                symbolType="class",
                parentSymbol=parent_qualified_name,
                signature=signature,
                coveredLineRanges=((start_line, end_line),),
            )
        ]

    chunks = [
        PythonChunkSpec(
            startLine=start_line,
            endLine=end_line,
            content=_build_large_class_summary_content(node=node, signature=signature),
            contentType=content_type,
            symbolName=node.name,
            qualifiedSymbolName=qualified_symbol_name,
            symbolType="class",
            parentSymbol=parent_qualified_name,
            signature=signature,
        )
    ]
    chunks.extend(
        _build_scope_chunks(
            nodes=node.body,
            source_lines=source_lines,
            file_content_type=file_content_type,
            class_max_lines=class_max_lines,
            parent_qualified_name=qualified_symbol_name,
            include_context_chunks=False,
        )
    )
    return chunks


def _resolve_symbol_content_type(file_content_type: str) -> str:
    if file_content_type == CODE_CONTEXT_CONTENT_TYPE:
        return CODE_SYMBOL_CONTENT_TYPE
    return file_content_type


def _qualify_symbol(parent_qualified_name: str | None, symbol_name: str) -> str:
    if not parent_qualified_name:
        return symbol_name
    return f"{parent_qualified_name}.{symbol_name}"


def _slice_source(source_lines: list[str], start_line: int, end_line: int) -> str:
    return "\n".join(source_lines[start_line - 1 : end_line])


def _build_uncovered_source_chunks(
    *,
    specs: list[PythonChunkSpec],
    source_lines: list[str],
    content_type: str,
) -> list[PythonChunkSpec]:
    covered_lines = [False] * len(source_lines)

    for spec in specs:
        for start_line, end_line in spec.coveredLineRanges:
            for line_index in range(max(start_line, 1) - 1, min(end_line, len(source_lines))):
                covered_lines[line_index] = True

    chunks: list[PythonChunkSpec] = []
    line_index = 0
    while line_index < len(source_lines):
        if covered_lines[line_index]:
            line_index += 1
            continue

        range_start = line_index
        while line_index < len(source_lines) and not covered_lines[line_index]:
            line_index += 1
        range_end = line_index - 1

        nonblank_indexes = [
            idx for idx in range(range_start, range_end + 1) if source_lines[idx].strip()
        ]
        if not nonblank_indexes:
            continue

        trimmed_start = nonblank_indexes[0]
        trimmed_end = nonblank_indexes[-1]
        start_line = trimmed_start + 1
        end_line = trimmed_end + 1
        chunks.append(
            PythonChunkSpec(
                startLine=start_line,
                endLine=end_line,
                content=_slice_source(source_lines, start_line, end_line),
                contentType=content_type,
                coveredLineRanges=((start_line, end_line),),
            )
        )

    return chunks


def _node_span(node: ast.AST) -> tuple[int, int]:
    start_line = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", [])
    for decorator in decorators:
        decorator_line = getattr(decorator, "lineno", start_line)
        start_line = min(start_line, decorator_line)
    end_line = getattr(node, "end_lineno", start_line)
    return start_line, end_line


def _build_signature(
    *,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
) -> str | None:
    start_line, end_line = _node_span(node)
    block_lines = source_lines[start_line - 1 : end_line]
    if not block_lines:
        return None

    signature_lines: list[str] = []
    started = False
    for line in block_lines:
        stripped = line.strip()
        if not started and not _is_signature_line(stripped):
            continue
        if not stripped:
            continue
        started = True
        signature_lines.append(stripped)
        if stripped.endswith(":"):
            break

    if not signature_lines:
        return None

    return " ".join(signature_lines)


def _is_signature_line(value: str) -> bool:
    return value.startswith("def ") or value.startswith("async def ") or value.startswith("class ")


def _build_large_class_summary_content(
    *,
    node: ast.ClassDef,
    signature: str | None,
) -> str:
    parts = [signature or f"class {node.name}:"]

    docstring = ast.get_docstring(node)
    if docstring:
        parts.append(f"docstring: {_truncate_inline_text(docstring)}")

    attribute_names = _collect_class_attribute_names(node)
    if attribute_names:
        parts.append(f"class_attributes: {', '.join(attribute_names)}")

    method_names = [child.name for child in node.body if isinstance(child, _FUNCTION_NODE_TYPES)]
    if method_names:
        parts.append(f"methods: {', '.join(method_names)}")

    nested_class_names = [child.name for child in node.body if isinstance(child, ast.ClassDef)]
    if nested_class_names:
        parts.append(f"nested_classes: {', '.join(nested_class_names)}")

    return "\n".join(parts)


def _collect_class_attribute_names(node: ast.ClassDef) -> list[str]:
    names: list[str] = []

    for child in node.body:
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            names.append(child.target.id)

    return names


def _truncate_inline_text(value: str, max_chars: int = _DOCSTRING_MAX_CHARS) -> str:
    normalized = " ".join(value.strip().split())
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 3:
        return normalized[:max_chars]
    return f"{normalized[:max_chars - 3].rstrip()}..."
