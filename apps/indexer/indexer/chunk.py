from __future__ import annotations

import hashlib
from pathlib import Path

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
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def make_chunk_id(path: str, start: int, end: int, content_hash: str) -> str:
    composed = f"{path}:{start}:{end}:{content_hash}"
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


def chunk_file(
    file_path: Path,
    repo_root: Path,
    chunk_lines: int,
    overlap: int,
    as_posix: bool,
) -> dict:
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
    content_hash = hash_content(text)
    language = detect_language(resolved_file)

    blocks = _chunk_lines_impl(
        lines=lines,
        chunk_lines=chunk_lines,
        overlap=overlap,
    )

    chunks = [
        {
            "chunkId": make_chunk_id(normalized_path, start, end, content_hash),
            "contentHash": content_hash,
            "path": normalized_path,
            "startLine": start,
            "endLine": end,
            "language": language,
            "content": "\n".join(chunk_content),
        }
        for start, end, chunk_content in blocks
    ]

    return {
        "path": normalized_path,
        "pathIsRelative": path_is_relative,
        "totalLines": len(lines),
        "encoding": encoding,
        "chunks": chunks,
        "warnings": warnings,
    }
