from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHUNK_SCHEMA_VERSION = "v5"
LINE_WINDOW_CHUNK_STRATEGY = "line_window"
PYTHON_SYMBOL_CHUNK_STRATEGY = "python_symbol"
TS_SYMBOL_CHUNK_STRATEGY = "ts_symbol"
DOC_SECTION_CHUNK_STRATEGY = "doc_section"
CONFIG_SECTION_CHUNK_STRATEGY = "config_section"
SQL_STATEMENT_CHUNK_STRATEGY = "sql_statement"


def _normalize_serialized_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_normalize_serialized_value(item) for item in value]
    if isinstance(value, list):
        return [_normalize_serialized_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_serialized_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class ChunkDocument:
    chunkId: str
    contentHash: str
    path: str
    startLine: int
    endLine: int
    language: str
    content: str
    chunkSchemaVersion: str = CHUNK_SCHEMA_VERSION
    contentType: str | None = None
    collectionContentType: str | None = None
    symbolName: str | None = None
    qualifiedSymbolName: str | None = None
    symbolType: str | None = None
    parentSymbol: str | None = None
    signature: str | None = None
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    callers: tuple[str, ...] = ()
    callees: tuple[str, ...] = ()
    summaryText: str | None = None
    contextText: str | None = None
    chunkStrategy: str = LINE_WINDOW_CHUNK_STRATEGY

    def to_dict(self) -> dict[str, object]:
        return _normalize_serialized_value(asdict(self))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class ChunkFileResult:
    path: str
    pathIsRelative: bool
    totalLines: int
    encoding: str
    chunks: tuple[ChunkDocument, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return _normalize_serialized_value(asdict(self))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    document: ChunkDocument
    chunkIndex: int
    fileMtime: float
    fileSize: int

    @staticmethod
    def _repo_identity(*, repo: str, repo_root: Path) -> str:
        return f"{repo}:{repo_root}"

    def to_qdrant_payload(self, *, repo: str, repo_root: Path) -> dict[str, object]:
        document = self.document
        return {
            "repo": repo,
            "path": document.path,
            "chunk_index": self.chunkIndex,
            "chunk_id": document.chunkId,
            "content_hash": document.contentHash,
            "chunk_schema_version": document.chunkSchemaVersion,
            "chunk_strategy": document.chunkStrategy,
            "ext": Path(document.path).suffix.lower(),
            "mtime": self.fileMtime,
            "size_bytes": self.fileSize,
            "text_len": len(document.content),
            "start_line": document.startLine,
            "end_line": document.endLine,
            "language": document.language,
            "content_type": document.collectionContentType,
            "chunk_content_type": document.contentType,
            "source": "repo",
            "repo_root": str(repo_root),
            "text": document.content,
            "symbol_name": document.symbolName,
            "qualified_symbol_name": document.qualifiedSymbolName,
            "symbol_type": document.symbolType,
            "parent_symbol": document.parentSymbol,
            "signature": document.signature,
            "imports": list(document.imports),
            "exports": list(document.exports),
            "callers": list(document.callers),
            "callees": list(document.callees),
            "summary_text": document.summaryText,
            "context_text": document.contextText,
        }

    def point_id(self, *, repo: str, repo_root: Path) -> str:
        identity = self._repo_identity(repo=repo, repo_root=repo_root)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{identity}:{self.document.chunkId}"))

    def to_qdrant_point(
        self,
        *,
        repo: str,
        repo_root: Path,
        vector: list[float],
    ) -> dict[str, object]:
        return {
            "id": self.point_id(repo=repo, repo_root=repo_root),
            "vector": vector,
            "payload": self.to_qdrant_payload(repo=repo, repo_root=repo_root),
        }
