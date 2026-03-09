from __future__ import annotations

import hashlib
from pathlib import Path

from .config import RuntimeConfig
from .content_classification import (
    CONFIG_BLOCK_CONTENT_TYPE,
    SQL_BLOCK_CONTENT_TYPE,
    classify_content_type,
    resolve_collection_content_type,
)
from .chunk_models import (
    ChunkDocument,
    ChunkFileResult,
    LINE_WINDOW_CHUNK_STRATEGY,
)
from .chunk_python import PythonChunkSpec, chunk_python_source

_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".py": "python",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}
_SUMMARY_FIRST_LINE_MAX_CHARS = 120
_CONTEXT_PREVIEW_MAX_CHARS = 280


def read_text(path: Path) -> tuple[str, str]:
    encodings: tuple[tuple[str, str], ...] = (
        ("utf-8", "strict"),
        ("utf-8-sig", "strict"),
        ("latin-1", "replace"),
    )

    last_decode_error: UnicodeDecodeError | None = None
    for encoding, errors in encodings:
        try:
            with path.open("r", encoding=encoding, errors=errors) as handle:
                text = handle.read()
                if encoding == "utf-8" and text.startswith("\ufeff"):
                    continue
                return text, encoding
        except UnicodeDecodeError as exc:
            last_decode_error = exc

    if last_decode_error is not None:
        raise last_decode_error

    raise RuntimeError("Não foi possível ler arquivo texto")


def _chunk_lines_impl(
    lines: list[str],
    chunk_lines: int,
    overlap: int,
) -> list[tuple[int, int, list[str]]]:
    if not lines:
        return []

    step = chunk_lines - overlap
    chunks: list[tuple[int, int, list[str]]] = []
    start_index = 0

    while start_index < len(lines):
        end_index = min(start_index + chunk_lines, len(lines))
        block = lines[start_index:end_index]
        if block:
            chunks.append((start_index + 1, end_index, block))

        if end_index >= len(lines):
            break

        start_index += step

    return chunks


def chunk_lines(
    lines: list[str],
    chunk_lines: int,
    overlap: int,
) -> list[tuple[int, int, list[str]]]:
    if chunk_lines <= 0:
        raise ValueError("chunk_lines deve ser maior que 0")
    if overlap < 0:
        raise ValueError("overlap deve ser maior ou igual a 0")
    if overlap >= chunk_lines:
        raise ValueError("overlap deve ser menor que chunk_lines")

    return _chunk_lines_impl(lines=lines, chunk_lines=chunk_lines, overlap=overlap)


def hash_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def make_chunk_id(
    path: str,
    start: int,
    end: int,
    language: str,
    *,
    qualified_symbol_name: str | None = None,
    symbol_type: str | None = None,
    signature: str | None = None,
) -> str:
    if qualified_symbol_name:
        composed = (
            f"{path}:{language}:{qualified_symbol_name}:{symbol_type or 'symbol'}:"
            f"{signature or 'no-signature'}"
        )
    else:
        composed = f"{path}:{start}:{end}:{language}"
    return hashlib.sha256(composed.encode("utf-8")).hexdigest()


def normalize_path(file_path: Path, repo_root: Path, as_posix: bool) -> str:
    resolved_file = file_path.resolve()
    resolved_root = repo_root.resolve()

    try:
        normalized_path: Path = resolved_file.relative_to(resolved_root)
    except ValueError:
        normalized_path = resolved_file

    if as_posix:
        return normalized_path.as_posix()

    return str(normalized_path)


def detect_language(path: Path) -> str:
    return _LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")


def _collapse_inline_text(value: str) -> str:
    return " ".join(value.strip().split())


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return f"{value[: max_chars - 3].rstrip()}..."


def _first_useful_line(content: str) -> str | None:
    for line in content.splitlines():
        normalized = _collapse_inline_text(line)
        if normalized:
            return _truncate_text(normalized, _SUMMARY_FIRST_LINE_MAX_CHARS)
    return None


def _content_preview(content: str) -> str | None:
    normalized = _collapse_inline_text(content)
    if not normalized:
        return None
    return _truncate_text(normalized, _CONTEXT_PREVIEW_MAX_CHARS)


def _format_line_range(start: int, end: int) -> str:
    if start == end:
        return f"line {start}"
    return f"lines {start}-{end}"


def _build_summary_text(
    *,
    path: str,
    language: str,
    start_line: int,
    end_line: int,
    content_type: str | None,
    content: str,
    symbol_name: str | None = None,
    qualified_symbol_name: str | None = None,
    symbol_type: str | None = None,
) -> str:
    parts = [
        path,
        language,
        _format_line_range(start_line, end_line),
        f"type={content_type or 'unknown'}",
    ]
    if qualified_symbol_name:
        parts.append(f"symbol={qualified_symbol_name}")
    elif symbol_name:
        parts.append(f"symbol={symbol_name}")
    if symbol_type:
        parts.append(f"symbol_type={symbol_type}")
    first_line = _first_useful_line(content)
    if first_line:
        parts.append(f"first_line={first_line}")
    return " | ".join(parts)


def _build_context_text(
    *,
    path: str,
    language: str,
    start_line: int,
    end_line: int,
    content_type: str | None,
    chunk_strategy: str,
    content: str,
    qualified_symbol_name: str | None = None,
    symbol_type: str | None = None,
    parent_symbol: str | None = None,
    signature: str | None = None,
) -> str:
    lines = [
        f"Path: {path}",
        f"Language: {language}",
        f"Range: {_format_line_range(start_line, end_line)}",
        f"Type: {content_type or 'unknown'}",
        f"Chunk strategy: {chunk_strategy}",
    ]
    if qualified_symbol_name:
        lines.append(f"Symbol: {qualified_symbol_name}")
    if symbol_type:
        lines.append(f"Symbol type: {symbol_type}")
    if parent_symbol:
        lines.append(f"Parent symbol: {parent_symbol}")
    if signature:
        lines.append(f"Signature: {signature}")
    preview = _content_preview(content)
    if preview:
        lines.append(f"Preview: {preview}")
    return "\n".join(lines)


def _should_use_python_symbol_chunking(
    *,
    language: str,
    content_type: str,
    collection_content_type: str,
) -> bool:
    if language != "python":
        return False
    if collection_content_type != "code":
        return False
    return content_type not in {CONFIG_BLOCK_CONTENT_TYPE, SQL_BLOCK_CONTENT_TYPE}


def _build_chunk_document(
    *,
    path: str,
    language: str,
    content: str,
    start_line: int,
    end_line: int,
    content_type: str,
    chunk_strategy: str,
    collection_content_type: str,
    symbol_name: str | None = None,
    qualified_symbol_name: str | None = None,
    symbol_type: str | None = None,
    parent_symbol: str | None = None,
    signature: str | None = None,
) -> ChunkDocument:
    summary_text = _build_summary_text(
        path=path,
        language=language,
        start_line=start_line,
        end_line=end_line,
        content_type=content_type,
        content=content,
        symbol_name=symbol_name,
        qualified_symbol_name=qualified_symbol_name,
        symbol_type=symbol_type,
    )
    context_text = _build_context_text(
        path=path,
        language=language,
        start_line=start_line,
        end_line=end_line,
        content_type=content_type,
        chunk_strategy=chunk_strategy,
        content=content,
        qualified_symbol_name=qualified_symbol_name,
        symbol_type=symbol_type,
        parent_symbol=parent_symbol,
        signature=signature,
    )

    return ChunkDocument(
        chunkId=make_chunk_id(
            path,
            start_line,
            end_line,
            language,
            qualified_symbol_name=qualified_symbol_name,
            symbol_type=symbol_type,
            signature=signature,
        ),
        contentHash=hash_content(content),
        path=path,
        startLine=start_line,
        endLine=end_line,
        language=language,
        content=content,
        contentType=content_type,
        collectionContentType=collection_content_type,
        symbolName=symbol_name,
        qualifiedSymbolName=qualified_symbol_name,
        symbolType=symbol_type,
        parentSymbol=parent_symbol,
        signature=signature,
        summaryText=summary_text,
        contextText=context_text,
        chunkStrategy=chunk_strategy,
    )


def chunk_file_documents(
    file_path: Path,
    repo_root: Path,
    chunk_lines: int,
    overlap: int,
    as_posix: bool,
    runtime_config: RuntimeConfig | None = None,
) -> ChunkFileResult:
    if chunk_lines <= 0:
        raise ValueError("chunk_lines deve ser maior que 0")
    if overlap < 0:
        raise ValueError("overlap deve ser maior ou igual a 0")
    if overlap >= chunk_lines:
        raise ValueError("overlap deve ser menor que chunk_lines")

    resolved_file = file_path.expanduser().resolve()
    resolved_root = repo_root.expanduser().resolve()

    if not resolved_file.exists() or not resolved_file.is_file():
        raise ValueError(f"Arquivo inválido ou inexistente: {resolved_file}")

    try:
        resolved_file.relative_to(resolved_root)
        path_is_relative = True
    except ValueError:
        path_is_relative = False

    normalized_path = normalize_path(
        file_path=resolved_file,
        repo_root=resolved_root,
        as_posix=as_posix,
    )

    warnings: list[str] = []
    if not path_is_relative:
        warnings.append("Arquivo fora de REPO_ROOT; usando path absoluto canônico")

    text, encoding = read_text(resolved_file)
    lines = text.splitlines()
    language = detect_language(resolved_file)
    content_type, _ = classify_content_type(normalized_path, runtime_config=runtime_config)
    collection_content_type = resolve_collection_content_type(content_type)
    chunks_list: list[ChunkDocument] = []

    python_specs: tuple[PythonChunkSpec, ...] | None = None
    if _should_use_python_symbol_chunking(
        language=language,
        content_type=content_type,
        collection_content_type=collection_content_type,
    ):
        python_specs = chunk_python_source(
            text=text,
            file_content_type=content_type,
            class_max_lines=chunk_lines,
        )

    if python_specs is not None and (python_specs or not text.strip()):
        for spec in python_specs:
            chunks_list.append(
                _build_chunk_document(
                    path=normalized_path,
                    language=language,
                    content=spec.content,
                    start_line=spec.startLine,
                    end_line=spec.endLine,
                    content_type=spec.contentType,
                    chunk_strategy=spec.chunkStrategy,
                    collection_content_type=resolve_collection_content_type(spec.contentType),
                    symbol_name=spec.symbolName,
                    qualified_symbol_name=spec.qualifiedSymbolName,
                    symbol_type=spec.symbolType,
                    parent_symbol=spec.parentSymbol,
                    signature=spec.signature,
                )
            )
    else:
        blocks = _chunk_lines_impl(
            lines=lines,
            chunk_lines=chunk_lines,
            overlap=overlap,
        )
        for start, end, chunk_content in blocks:
            chunks_list.append(
                _build_chunk_document(
                    path=normalized_path,
                    language=language,
                    content="\n".join(chunk_content),
                    start_line=start,
                    end_line=end,
                    content_type=content_type,
                    chunk_strategy=LINE_WINDOW_CHUNK_STRATEGY,
                    collection_content_type=collection_content_type,
                )
            )

    chunks = tuple(chunks_list)

    return ChunkFileResult(
        path=normalized_path,
        pathIsRelative=path_is_relative,
        totalLines=len(lines),
        encoding=encoding,
        chunks=chunks,
        warnings=tuple(warnings),
    )


def chunk_file(
    file_path: Path,
    repo_root: Path,
    chunk_lines: int,
    overlap: int,
    as_posix: bool,
    runtime_config: RuntimeConfig | None = None,
) -> dict:
    return chunk_file_documents(
        file_path=file_path,
        repo_root=repo_root,
        chunk_lines=chunk_lines,
        overlap=overlap,
        as_posix=as_posix,
        runtime_config=runtime_config,
    ).to_dict()
