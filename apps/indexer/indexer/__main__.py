from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .chunk import chunk_file, read_text
from .config import (
    ChunkConfig,
    RuntimeConfig,
    ScanConfig,
    load_chunk_config,
    load_runtime_config,
    load_scan_config,
)
from .env import load_env_files
from .embedder import EmbedderConfig, EmbedderError, OllamaEmbedder, load_embedder_config
from .qdrant_store import CONTENT_TYPE_FIELD, QdrantStore, QdrantStoreError, load_qdrant_config
from .scan import scan_repo

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

def _should_exclude_context_path(
    path: str | None,
    runtime_config: RuntimeConfig | None = None,
) -> bool:
    if not path:
        return False
    config = runtime_config or load_runtime_config()
    normalized = f"/{path.replace('\\', '/').strip('/')}/".lower()
    return any(marker in normalized for marker in config.excluded_context_path_parts)


def _filter_context_results(
    results: list[dict[str, object]],
    runtime_config: RuntimeConfig | None = None,
) -> tuple[list[dict[str, object]], int]:
    config = runtime_config or load_runtime_config()
    filtered: list[dict[str, object]] = []
    excluded = 0

    for result in results:
        payload = result.get("payload", {})
        path = payload.get("path") if isinstance(payload, dict) else None
        if isinstance(path, str) and _should_exclude_context_path(path, runtime_config=config):
            excluded += 1
            continue
        filtered.append(result)

    return filtered, excluded


def _normalize_snippet(text: str, max_chars: int | None = None) -> str:
    resolved_max_chars = max_chars or load_runtime_config().search_snippet_max_chars
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    if len(normalized) <= resolved_max_chars:
        return normalized
    return f"{normalized[: resolved_max_chars - 3].rstrip()}..."


def _coerce_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value > 0 else None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = int(raw)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    return None


def _resolve_search_line_range(payload: dict[str, object]) -> tuple[int, int] | None:
    start_line = _coerce_positive_int(payload.get("start_line", payload.get("startLine")))
    end_line = _coerce_positive_int(payload.get("end_line", payload.get("endLine")))

    if start_line is None or end_line is None:
        return None
    if end_line < start_line:
        return None

    return start_line, end_line


def _load_result_file_lines(
    *,
    payload: dict[str, object],
    line_cache: dict[Path, list[str]] | None = None,
) -> list[str] | None:
    path_value = payload.get("path")
    repo_root_value = payload.get("repo_root", payload.get("repoRoot"))

    if not isinstance(path_value, str) or not path_value.strip():
        return None
    if not isinstance(repo_root_value, str) or not repo_root_value.strip():
        return None

    path = Path(path_value)

    try:
        repo_root = Path(repo_root_value).expanduser().resolve()
    except OSError:
        return None

    candidate = path if path.is_absolute() else repo_root / path

    try:
        resolved_path = candidate.resolve()
    except OSError:
        return None

    try:
        resolved_path.relative_to(repo_root)
    except ValueError:
        return None

    if not resolved_path.is_file():
        return None

    if line_cache is not None and resolved_path in line_cache:
        return line_cache[resolved_path]

    try:
        text, _ = read_text(resolved_path)
    except (OSError, UnicodeDecodeError):
        return None

    lines = text.splitlines()
    if line_cache is not None:
        line_cache[resolved_path] = lines
    return lines


def _resolve_snippet_from_file(
    *,
    payload: dict[str, object],
    line_cache: dict[Path, list[str]] | None = None,
) -> str | None:
    line_range = _resolve_search_line_range(payload)
    if line_range is None:
        return None

    lines = _load_result_file_lines(payload=payload, line_cache=line_cache)
    if lines is None:
        return None

    start_line, end_line = line_range
    if start_line > len(lines):
        return None

    start_index = max(start_line - 1, 0)
    end_index = min(end_line, len(lines))
    if end_index <= start_index:
        return None

    snippet = "\n".join(lines[start_index:end_index]).strip()
    return snippet or None


def _resolve_search_snippet(
    *,
    payload: dict[str, object],
    line_cache: dict[Path, list[str]] | None = None,
) -> str | None:
    snippet_raw = payload.get("text")
    if isinstance(snippet_raw, str) and snippet_raw.strip():
        return snippet_raw

    return _resolve_snippet_from_file(payload=payload, line_cache=line_cache)


def _build_search_header(payload: dict[str, object]) -> str:
    repo = payload.get("repo")
    repo_prefix = f"[{repo}] " if isinstance(repo, str) and repo.strip() else ""
    path = payload.get("path", "?")
    start_line = payload.get("start_line", payload.get("startLine", "?"))
    end_line = payload.get("end_line", payload.get("endLine", "?"))
    return f"{repo_prefix}{path}:{start_line}-{end_line}"


def _format_search_result_block(
    *,
    index: int,
    score: float,
    payload: dict[str, object],
    vector: object | None = None,
    snippet_override: str | None = None,
) -> str:
    snippet_raw = snippet_override if snippet_override is not None else payload.get("text")
    snippet = "(no text payload)"
    if isinstance(snippet_raw, str) and snippet_raw.strip():
        snippet = _normalize_snippet(snippet_raw).replace('"', "'")

    lines = [
        f"[{index}] score={score:.4f}  {_build_search_header(payload)}",
        f'    snippet: "{snippet}"',
    ]

    if vector is not None:
        lines.append(f"    vector: {vector}")

    return "\n".join(lines)


def _build_search_filters(args: argparse.Namespace) -> dict[str, object] | None:
    filters: dict[str, object] = {}

    if getattr(args, "ext", None):
        filters["ext"] = args.ext
    if getattr(args, "language", None):
        filters["language"] = args.language
    if getattr(args, "path_prefix", None):
        filters["path_prefix"] = args.path_prefix

    return filters or None


def _find_doc_path_hint(
    path: str,
    runtime_config: RuntimeConfig | None = None,
) -> str | None:
    config = runtime_config or load_runtime_config()
    normalized = f"/{path.replace('\\', '/').strip('/').lower()}"
    for hint in config.doc_path_hints:
        if hint in normalized:
            return hint
    return None


def _classify_content_type(
    path: str,
    runtime_config: RuntimeConfig | None = None,
) -> tuple[str, str | None]:
    config = runtime_config or load_runtime_config()
    ext = Path(path).suffix.lower()
    path_hint = _find_doc_path_hint(path, runtime_config=config)
    if path_hint is not None or ext in config.doc_extensions:
        return "docs", path_hint
    return "code", path_hint


def _build_classification_log_record(
    *,
    file_path: str,
    ext: str,
    path_hint: str | None,
    classified_as: str,
) -> dict[str, object]:
    return {
        "file": file_path,
        "ext": ext,
        "path_hint": path_hint,
        "classified_as": classified_as,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _resolve_min_file_coverage(runtime_config: RuntimeConfig | None = None) -> float:
    config = runtime_config or load_runtime_config()
    return config.min_file_coverage


def _parse_scope_repos(raw_repos: str) -> list[str]:
    repos = [item.strip() for item in raw_repos.split(",")]
    normalized = [item for item in repos if item]
    if not normalized:
        raise ValueError("Erro: --scope-repos deve conter ao menos um repo")
    return normalized


def _build_ask_scope_payload(args: argparse.Namespace) -> dict[str, object]:
    if getattr(args, "scope_repo", None):
        return {
            "scope": {
                "type": "repo",
                "repo": args.scope_repo,
            }
        }

    if getattr(args, "scope_repos", None):
        return {
            "scope": {
                "type": "repos",
                "repos": _parse_scope_repos(args.scope_repos),
            }
        }

    if getattr(args, "scope_all", False):
        return {
            "scope": {
                "type": "all",
            }
        }

    raise ValueError(
        "Erro: informe um escopo (--scope-repo, --scope-repos, --scope-all)"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m indexer")
    subparsers = parser.add_subparsers(dest="command")

    # Comando scan
    scan_parser = subparsers.add_parser("scan", help="Escaneia o repositório")
    scan_parser.add_argument("--repo-root", dest="repo_root", default=None)
    scan_parser.add_argument("--allow-exts", dest="allow_exts", default=None)
    scan_parser.add_argument("--ignore-dirs", dest="ignore_dirs", default=None)
    scan_parser.add_argument("--max-files", dest="max_files", type=int, default=None)
    scan_parser.add_argument(
        "--ignore-patterns", dest="ignore_patterns", default=None,
        help="Padrões glob para ignorar arquivos (CSV). Ex: '*.md,docs/*'. Prioridade: CLI > Env (SCAN_IGNORE_PATTERNS) > Default.",
    )

    # Comando chunk
    chunk_parser = subparsers.add_parser("chunk", help="Gera chunks de um arquivo")
    chunk_parser.add_argument("--file", dest="file", required=True)
    chunk_parser.add_argument("--chunk-lines", dest="chunk_lines", type=int, default=None)
    chunk_parser.add_argument("--overlap-lines", dest="overlap_lines", type=int, default=None)
    chunk_parser.add_argument("--repo-root", dest="repo_root", default=None)
    chunk_parser.add_argument(
        "--as-posix",
        dest="as_posix",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    # Comando init
    init_parser = subparsers.add_parser(
        "init", help="Inicializa collection no Qdrant (idempotente)"
    )
    init_parser.add_argument(
        "--api-url-code",
        dest="api_url_code",
        default=None,
        help="URL da API de embedding para code (env: EMBEDDING_PROVIDER_CODE_API_URL)",
    )
    init_parser.add_argument(
        "--api-url-docs",
        dest="api_url_docs",
        default=None,
        help="URL da API de embedding para docs (env: EMBEDDING_PROVIDER_DOCS_API_URL)",
    )
    init_parser.add_argument(
        "--api-key-code",
        dest="api_key_code",
        default=None,
        help="API key de embedding para code (env: EMBEDDING_PROVIDER_CODE_API_KEY)",
    )
    init_parser.add_argument(
        "--api-key-docs",
        dest="api_key_docs",
        default=None,
        help="API key de embedding para docs (env: EMBEDDING_PROVIDER_DOCS_API_KEY)",
    )
    init_parser.add_argument(
        "--provider-code",
        dest="provider_code",
        default=None,
        help="Provider de embedding para code (env: EMBEDDING_PROVIDER_CODE)",
    )
    init_parser.add_argument(
        "--provider-docs",
        dest="provider_docs",
        default=None,
        help="Provider de embedding para docs (env: EMBEDDING_PROVIDER_DOCS)",
    )
    init_parser.add_argument(
        "--model-code",
        dest="model_code",
        default=None,
        help="Modelo de embedding para code (env: EMBEDDING_MODEL_CODE)",
    )
    init_parser.add_argument(
        "--model-docs",
        dest="model_docs",
        default=None,
        help="Modelo de embedding para docs (env: EMBEDDING_MODEL_DOCS)",
    )
    init_parser.add_argument(
        "--qdrant-url", dest="qdrant_url", default=None, help="URL do Qdrant"
    )

    # Comando index
    index_parser = subparsers.add_parser(
        "index", help="Indexa repositório: scan → chunk → embed → upsert"
    )
    index_parser.add_argument("--repo-root", dest="repo_root", default=None)
    index_parser.add_argument("--allow-exts", dest="allow_exts", default=None)
    index_parser.add_argument("--ignore-dirs", dest="ignore_dirs", default=None)
    index_parser.add_argument("--max-files", dest="max_files", type=int, default=None)
    index_parser.add_argument("--chunk-lines", dest="chunk_lines", type=int, default=None)
    index_parser.add_argument("--overlap-lines", dest="overlap_lines", type=int, default=None)
    index_parser.add_argument(
        "--ignore-patterns", dest="ignore_patterns", default=None,
        help="Padrões glob para ignorar arquivos (CSV). Ex: '*.md,docs/*'. Prioridade: CLI > Env (SCAN_IGNORE_PATTERNS) > Default.",
    )

    # Comando search
    search_parser = subparsers.add_parser(
        "search", help="Busca semântica na collection indexada"
    )
    search_parser.add_argument("query", help="Texto da busca")
    search_parser.add_argument(
        "-k", "--top-k", "--topk",
        dest="top_k",
        type=int,
        default=10,
        help="Número de resultados (default: 10)"
    )
    search_parser.add_argument(
        "--path_prefix",
        dest="path_prefix",
        default=None,
        help="Filtra por prefixo de path no payload"
    )
    search_parser.add_argument(
        "--with_vector",
        dest="with_vector",
        action="store_true",
        help="Inclui vetor no output"
    )
    search_parser.add_argument(
        "--ext",
        dest="ext",
        help="Filtrar por extensão (ex: .py)"
    )
    search_parser.add_argument(
        "--language",
        dest="language",
        help="Filtrar por linguagem (ex: python)"
    )
    search_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output em JSON"
    )
    search_parser.add_argument(
        "--content-type",
        dest="content_type",
        choices=["code", "docs", "all"],
        default="all",
        help="Filtrar por tipo de conteúdo indexado (code, docs, all).",
    )

    # Comando ask (RAG - Retrieval Augmented Generation)
    ask_parser = subparsers.add_parser(
        "ask", help="Pergunta ao LLM usando contexto do código indexado (RAG)"
    )
    ask_parser.add_argument("question", help="Pergunta em linguagem natural")
    ask_parser.add_argument(
        "-k", "--top-k",
        dest="top_k",
        type=int,
        default=5,
        help="Número de chunks de contexto (default: 5)"
    )
    ask_parser.add_argument(
        "--model",
        dest="llm_model",
        default=None,
        help="Modelo LLM para resposta (default: env LLM_MODEL ou gpt-oss:latest)"
    )
    ask_parser.add_argument(
        "--ext",
        dest="ext",
        help="Filtrar contexto por extensão (ex: .py)"
    )
    ask_parser.add_argument(
        "--show-context",
        dest="show_context",
        action="store_true",
        help="Mostrar chunks de contexto usados"
    )
    ask_parser.add_argument(
        "--min-score",
        dest="min_score",
        type=float,
        default=0.6,
        help="Score mínimo de similaridade (default: 0.6). Chunks abaixo são ignorados."
    )
    ask_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output em JSON"
    )
    ask_parser.add_argument(
        "--content-type",
        dest="content_type",
        choices=["code", "docs", "all"],
        default="all",
        help="Tipo de conteúdo alvo no MCP (code, docs, all).",
    )
    ask_parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        help="Falha em vez de retorno parcial quando uma coleção estiver indisponível.",
    )
    scope_group = ask_parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--scope-repo",
        dest="scope_repo",
        default=None,
        help="Escopo de um único repo",
    )
    scope_group.add_argument(
        "--scope-repos",
        dest="scope_repos",
        default=None,
        help="Escopo de vários repos (lista separada por vírgula)",
    )
    scope_group.add_argument(
        "--scope-all",
        dest="scope_all",
        action="store_true",
        help="Escopo global (requer ALLOW_GLOBAL_SCOPE=true no MCP server)",
    )

    return parser


def _resolve_scan_config(args: argparse.Namespace) -> ScanConfig:
    return load_scan_config(
        repo_root=args.repo_root,
        ignore_dirs=args.ignore_dirs,
        allow_exts=args.allow_exts,
        ignore_patterns=getattr(args, "ignore_patterns", None),
    )


def _resolve_chunk_config(args: argparse.Namespace) -> ChunkConfig:
    return load_chunk_config(
        repo_root=args.repo_root,
        chunk_lines=args.chunk_lines,
        overlap_lines=args.overlap_lines,
    )


def _scan_command(args: argparse.Namespace) -> int:
    config = _resolve_scan_config(args)

    if not config.repo_root.exists() or not config.repo_root.is_dir():
        print(
            f"Erro: REPO_ROOT inválido ou inexistente: {config.repo_root}",
            file=sys.stderr,
        )
        return 1

    files, stats = scan_repo(
        repo_root=config.repo_root,
        ignore_dirs=config.ignore_dirs,
        allow_exts=config.allow_exts,
        max_files=args.max_files,
        ignore_patterns=config.ignore_patterns,
    )

    payload = {
        "repoRoot": str(config.repo_root),
        "ignoreDirs": sorted(config.ignore_dirs),
        "allowExts": sorted(config.allow_exts),
        "stats": stats,
        "files": [Path(path).as_posix() for path in files],
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _chunk_command(args: argparse.Namespace) -> int:
    try:
        config = _resolve_chunk_config(args)
        result = chunk_file(
            file_path=Path(args.file),
            repo_root=config.repo_root,
            chunk_lines=config.chunk_lines,
            overlap=config.overlap_lines,
            as_posix=args.as_posix,
        )
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    payload = {
        "file": str(Path(args.file).expanduser().resolve()),
        "repoRoot": str(config.repo_root),
        "path": result["path"],
        "pathIsRelative": result["pathIsRelative"],
        "asPosix": args.as_posix,
        "chunkLines": config.chunk_lines,
        "overlapLines": config.overlap_lines,
        "totalLines": result["totalLines"],
        "encoding": result["encoding"],
        "chunks": result["chunks"],
        "stats": {"chunks": len(result["chunks"])},
        "warnings": result["warnings"],
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _init_command(args: argparse.Namespace) -> int:
    """
    Inicializa collections no Qdrant para code/docs.

    1. Probe vector_size via provider de embedding
    2. Resolve/gera collection_names
    3. Cria/valida collections no Qdrant
    4. Cria índice payload KEYWORD para content_type (idempotente)
    """
    try:
        runtime_config = load_runtime_config()

        # Carregar configs de embedding por tipo de conteúdo
        embedder_configs: dict[str, EmbedderConfig] = {}
        for content_type in runtime_config.content_types:
            embedder_configs[content_type] = load_embedder_config(
                content_type=content_type,
                api_url=getattr(args, f"api_url_{content_type}", None),
                api_key=getattr(args, f"api_key_{content_type}", None),
                provider=getattr(args, f"provider_{content_type}", None),
                model=getattr(args, f"model_{content_type}", None),
            )

        qdrant_config = load_qdrant_config(
            url=args.qdrant_url,
        )

        vector_sizes: dict[str, int] = {}
        for content_type in runtime_config.content_types:
            config = embedder_configs[content_type]
            logger.info(
                "Embedding config [%s]: provider=%s model=%s api_url=%s",
                content_type,
                config.provider,
                config.model,
                config.api_url,
            )
            with OllamaEmbedder(config) as embedder:
                vector_size = embedder.probe_vector_size()
                vector_sizes[content_type] = vector_size
                logger.info("Vector size [%s]: %s", content_type, vector_size)

        # Conectar ao Qdrant e garantir collections
        collections_result: dict[str, dict[str, object]] = {}
        payload_index_ok: dict[str, bool] = {}
        with QdrantStore(qdrant_config) as store:
            reference_content_type = runtime_config.content_types[0]
            collection_names = store.resolve_split_collection_names(
                vector_size=vector_sizes[reference_content_type],
                model_name=embedder_configs[reference_content_type].model,
            )
            logger.info(
                "Collections resolved: code=%s docs=%s",
                collection_names["code"],
                collection_names["docs"],
            )

            for content_type in runtime_config.content_types:
                collection_name = collection_names[content_type]
                result = store.ensure_collection(
                    collection_name=collection_name,
                    vector_size=vector_sizes[content_type],
                )
                collections_result[content_type] = result

                store.ensure_payload_keyword_index(
                    collection_name=collection_name,
                    field_name=CONTENT_TYPE_FIELD,
                )
                payload_index_ok[content_type] = store.has_payload_field(
                    collection_name=collection_name,
                    field_name=CONTENT_TYPE_FIELD,
                )

        # Output JSON
        output = {
            "embedding": {
                content_type: {
                    "provider": embedder_configs[content_type].provider,
                    "api_url": embedder_configs[content_type].api_url,
                    "model": embedder_configs[content_type].model,
                    "vector_size": vector_sizes[content_type],
                }
                for content_type in runtime_config.content_types
            },
            "collections": {
                content_type: {
                    "name": collections_result[content_type]["collection"],
                    "action": collections_result[content_type]["action"],
                }
                for content_type in runtime_config.content_types
            },
            "distance": qdrant_config.distance,
            "qdrant_url": qdrant_config.url,
            "payload_index": {
                CONTENT_TYPE_FIELD: {
                    "schema": "keyword",
                    "status": payload_index_ok,
                }
            },
        }

        if not all(payload_index_ok.values()):
            raise QdrantStoreError(
                f"Índice de payload '{CONTENT_TYPE_FIELD}' não está disponível em todas as collections"
            )

        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    except EmbedderError as exc:
        print(f"Erro no embedder: {exc}", file=sys.stderr)
        return 1
    except QdrantStoreError as exc:
        print(f"Erro no Qdrant: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Erro inesperado: {exc}", file=sys.stderr)
        return 1


def _make_point_id(rel_path: str, chunk_index: int, content_hash: str) -> str:
    """
    Gera ID determinístico para um ponto como UUID.
    
    Usa UUID v5 (namespace-based) para converter o hash composto em UUID válido.
    Isso garante IDs estáveis e reproduzíveis.
    """
    import uuid
    composed = f"{rel_path}:{chunk_index}:{content_hash}"
    # UUID v5 usa namespace + name para gerar UUID determinístico
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, composed))


def _index_command(args: argparse.Namespace) -> int:
    """
    Pipeline completo: scan → chunk → embed → upsert.

    1. Scan do repositório
    2. Chunk de cada arquivo
    3. Embed em batches
    4. Upsert no Qdrant com IDs estáveis
    """
    started = perf_counter()

    try:
        runtime_config = load_runtime_config()

        # Configs
        scan_config = _resolve_scan_config(args)
        chunk_config = _resolve_chunk_config(args)
        embedder_configs: dict[str, EmbedderConfig] = {
            content_type: load_embedder_config(content_type=content_type)
            for content_type in runtime_config.content_types
        }
        qdrant_config = load_qdrant_config()

        if not scan_config.repo_root.exists() or not scan_config.repo_root.is_dir():
            print(
                f"Erro: REPO_ROOT inválido ou inexistente: {scan_config.repo_root}",
                file=sys.stderr,
            )
            return 1

        logger.info(f"Repo root: {scan_config.repo_root}")

        vector_sizes: dict[str, int] = {}
        for content_type in runtime_config.content_types:
            config = embedder_configs[content_type]
            logger.info(
                "Embedding config [%s]: provider=%s model=%s api_url=%s",
                content_type,
                config.provider,
                config.model,
                config.api_url,
            )
            with OllamaEmbedder(config) as embedder:
                vector_sizes[content_type] = embedder.probe_vector_size()

        with QdrantStore(qdrant_config) as store:
            reference_content_type = runtime_config.content_types[0]
            collection_names = store.resolve_split_collection_names(
                vector_size=vector_sizes[reference_content_type],
                model_name=embedder_configs[reference_content_type].model,
            )
            for content_type in runtime_config.content_types:
                target_collection = collection_names[content_type]
                store.ensure_collection(
                    collection_name=target_collection,
                    vector_size=vector_sizes[content_type],
                )
                store.ensure_payload_keyword_index(
                    collection_name=target_collection,
                    field_name=CONTENT_TYPE_FIELD,
                )

        logger.info(
            "Collections: code=%s docs=%s",
            collection_names["code"],
            collection_names["docs"],
        )

        # 2. Scan
        logger.info("Iniciando scan...")
        files, scan_stats = scan_repo(
            repo_root=scan_config.repo_root,
            ignore_dirs=scan_config.ignore_dirs,
            allow_exts=scan_config.allow_exts,
            max_files=args.max_files,
            ignore_patterns=scan_config.ignore_patterns,
        )
        logger.info(f"Arquivos encontrados: {len(files)}")

        # 3. Chunk todos os arquivos
        logger.info("Iniciando chunking...")
        all_chunks: list[dict] = []
        chunk_errors: int = 0
        indexed_files: set[str] = set()
        min_coverage = _resolve_min_file_coverage(runtime_config)

        for file_path in files:
            abs_path = scan_config.repo_root / file_path
            ext = Path(file_path).suffix.lower()
            content_type, path_hint = _classify_content_type(
                str(file_path),
                runtime_config=runtime_config,
            )
            classification_log = _build_classification_log_record(
                file_path=str(file_path),
                ext=ext,
                path_hint=path_hint,
                classified_as=content_type,
            )
            logger.info("classification=%s", json.dumps(classification_log, ensure_ascii=False))
            try:
                result = chunk_file(
                    file_path=abs_path,
                    repo_root=scan_config.repo_root,
                    chunk_lines=chunk_config.chunk_lines,
                    overlap=chunk_config.overlap_lines,
                    as_posix=True,
                )
                for idx, chunk in enumerate(result["chunks"]):
                    chunk["_file_path"] = str(file_path)
                    chunk["_chunk_index"] = idx
                    chunk["_file_mtime"] = abs_path.stat().st_mtime
                    chunk["_file_size"] = abs_path.stat().st_size
                    chunk["_content_type"] = content_type
                    all_chunks.append(chunk)
                indexed_files.add(str(file_path))
            except Exception as exc:
                logger.warning(f"Erro ao chunkar {file_path}: {exc}")
                chunk_errors += 1

        logger.info(f"Total de chunks: {len(all_chunks)}")
        file_coverage = (len(indexed_files) / len(files)) if files else 1.0

        if not all_chunks:
            logger.warning("Nenhum chunk gerado. Encerrando.")
            output = {
                "status": "empty",
                "files_scanned": len(files),
                "files_indexed": len(indexed_files),
                "file_coverage": round(file_coverage, 4),
                "chunks_total": 0,
                "points_upserted": 0,
                "elapsed_ms": int((perf_counter() - started) * 1000),
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

        if file_coverage < min_coverage:
            output = {
                "status": "insufficient_coverage",
                "repo_root": str(scan_config.repo_root),
                "files_scanned": len(files),
                "files_indexed": len(indexed_files),
                "file_coverage": round(file_coverage, 4),
                "required_file_coverage": min_coverage,
                "chunk_errors": chunk_errors,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
            print(
                (
                    f"Cobertura de arquivos insuficiente: {file_coverage:.2%} "
                    f"(mínimo: {min_coverage:.2%})"
                ),
                file=sys.stderr,
            )
            return 1

        # 4. Embed em batches por tipo de conteúdo
        logger.info("Iniciando embedding...")
        chunks_by_type: dict[str, list[dict]] = {
            content_type: []
            for content_type in runtime_config.content_types
        }
        for chunk in all_chunks:
            chunks_by_type[chunk["_content_type"]].append(chunk)

        embeddings_by_type: dict[str, list[list[float]]] = {
            content_type: []
            for content_type in runtime_config.content_types
        }
        for content_type in runtime_config.content_types:
            target_chunks = chunks_by_type[content_type]
            if not target_chunks:
                continue

            config = embedder_configs[content_type]
            texts = [chunk["content"] for chunk in target_chunks]
            with OllamaEmbedder(config) as embedder:
                embeddings_by_type[content_type] = embedder.embed_texts_batched(
                    texts=texts,
                    expected_vector_size=vector_sizes[content_type],
                )

        embeddings_generated = sum(
            len(embeddings_by_type[content_type])
            for content_type in runtime_config.content_types
        )
        logger.info(f"Embeddings gerados: {embeddings_generated}")

        # 5. Montar pontos com IDs estáveis e payload rico
        logger.info("Montando pontos para upsert...")
        points_by_type: dict[str, list[dict]] = {
            content_type: []
            for content_type in runtime_config.content_types
        }

        for content_type in runtime_config.content_types:
            for chunk, embedding in zip(
                chunks_by_type[content_type],
                embeddings_by_type[content_type],
            ):
                # Derivar content_hash do chunk
                chunk_text = chunk["content"]
                content_hash = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()

                # ID estável
                point_id = _make_point_id(
                    rel_path=chunk["path"],
                    chunk_index=chunk["_chunk_index"],
                    content_hash=content_hash,
                )

                # Payload rico
                payload = {
                    "repo": scan_config.repo_root.name,
                    "path": chunk["path"],
                    "chunk_index": chunk["_chunk_index"],
                    "content_hash": content_hash,
                    "ext": Path(chunk["path"]).suffix.lower(),
                    "mtime": chunk["_file_mtime"],
                    "size_bytes": chunk["_file_size"],
                    "text_len": len(chunk_text),
                    "start_line": chunk["startLine"],
                    "end_line": chunk["endLine"],
                    "language": chunk["language"],
                    "content_type": chunk["_content_type"],
                    "source": "repo",
                    "repo_root": str(scan_config.repo_root),
                }

                point = {
                    "id": point_id,
                    "vector": embedding,
                    "payload": payload,
                }
                points_by_type[content_type].append(point)

        # 6. Upsert no Qdrant
        logger.info("Iniciando upsert no Qdrant...")
        upsert_results: dict[str, dict[str, int]] = {}
        with QdrantStore(qdrant_config) as store:
            for content_type in runtime_config.content_types:
                target_points = points_by_type[content_type]
                target_collection = collection_names[content_type]
                upsert_results[content_type] = store.upsert(
                    points=target_points,
                    collection_name=target_collection,
                )

        elapsed_ms = int((perf_counter() - started) * 1000)
        total_points_upserted = sum(item["points_upserted"] for item in upsert_results.values())

        # Output
        output = {
            "status": "success",
            "repo_root": str(scan_config.repo_root),
            "collections": collection_names,
            "files_scanned": len(files),
            "files_indexed": len(indexed_files),
            "file_coverage": round(file_coverage, 4),
            "required_file_coverage": min_coverage,
            "chunks_total": len(all_chunks),
            "chunks_by_type": {
                content_type: len(points_by_type[content_type])
                for content_type in runtime_config.content_types
            },
            "chunk_errors": chunk_errors,
            "embeddings_generated": embeddings_generated,
            "embeddings_generated_by_type": {
                content_type: len(embeddings_by_type[content_type])
                for content_type in runtime_config.content_types
            },
            "points_upserted": total_points_upserted,
            "upsert_by_type": upsert_results,
            "embedding": {
                content_type: {
                    "provider": embedder_configs[content_type].provider,
                    "model": embedder_configs[content_type].model,
                    "vector_size": vector_sizes[content_type],
                }
                for content_type in runtime_config.content_types
            },
            "elapsed_ms": elapsed_ms,
            "elapsed_sec": round(elapsed_ms / 1000, 2),
        }

        logger.info(
            f"Indexação concluída: {output['points_upserted']} pontos "
            f"em {output['elapsed_sec']}s"
        )

        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    except EmbedderError as exc:
        print(f"Erro no embedder: {exc}", file=sys.stderr)
        return 1
    except QdrantStoreError as exc:
        print(f"Erro no Qdrant: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("Erro inesperado")
        print(f"Erro inesperado: {exc}", file=sys.stderr)
        return 1


def _search_command(args: argparse.Namespace) -> int:
    """
    Busca semântica na collection indexada.
    
    1. Gera embedding da query
    2. Busca no Qdrant
    3. Exibe resultados
    """
    try:
        query = args.query.strip()
        if not query:
            print("Erro: query vazia.", file=sys.stderr)
            return 1

        runtime_config = load_runtime_config()
        qdrant_config = load_qdrant_config()
        content_type = getattr(args, "content_type", "all")
        if content_type in runtime_config.content_types:
            target_content_types = [content_type]
        else:
            target_content_types = list(runtime_config.content_types)

        embedder_configs: dict[str, EmbedderConfig] = {
            target_content_type: load_embedder_config(content_type=target_content_type)
            for target_content_type in target_content_types
        }

        query_vectors: dict[str, list[float]] = {}
        vector_sizes: dict[str, int] = {}
        for target_content_type in target_content_types:
            config = embedder_configs[target_content_type]
            with OllamaEmbedder(config) as embedder:
                embeddings = embedder.embed_texts([query])
                query_vector = embeddings[0]
                query_vectors[target_content_type] = query_vector
                vector_sizes[target_content_type] = len(query_vector)

        with QdrantStore(qdrant_config) as store:
            reference_content_type = target_content_types[0]
            collection_names = store.resolve_split_collection_names(
                vector_size=vector_sizes[reference_content_type],
                model_name=embedder_configs[reference_content_type].model,
            )
            filters = _build_search_filters(args)
            searched_collections: list[str] = [
                collection_names[target_content_type]
                for target_content_type in target_content_types
            ]
            merged: list[dict[str, object]] = []
            for target_content_type in target_content_types:
                merged.extend(
                    store.search(
                        query_vector=query_vectors[target_content_type],
                        collection_name=collection_names[target_content_type],
                        filters=filters,
                        top_k=args.top_k,
                        with_vector=args.with_vector,
                    )
                )

            if len(target_content_types) == 1:
                results = merged[: args.top_k]
            else:
                results = sorted(
                    merged,
                    key=lambda item: float(item.get("score", 0.0) or 0.0),
                    reverse=True,
                )[: args.top_k]

        if not results:
            print(
                f"Nenhum resultado nas collections {searched_collections} "
                "(collection ausente/vazia ou sem matches)."
            )
            return 0

        # Output
        if args.json_output:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"Query: \"{query}\"")
            print(f"Resultados: {len(results)}")
            print()

            line_cache: dict[Path, list[str]] = {}

            for i, r in enumerate(results, 1):
                payload = r.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}

                snippet = _resolve_search_snippet(payload=payload, line_cache=line_cache)

                block = _format_search_result_block(
                    index=i,
                    score=float(r.get("score", 0.0)),
                    payload=payload,
                    vector=r.get("vector") if args.with_vector else None,
                    snippet_override=snippet,
                )
                print(block)
                print()

        return 0

    except EmbedderError as exc:
        print(f"Erro no embedder: {exc}", file=sys.stderr)
        return 1
    except QdrantStoreError as exc:
        print(f"Qdrant indisponível: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("Erro inesperado")
        print(f"Erro inesperado: {exc}", file=sys.stderr)
        return 1


DEFAULT_LLM_MODEL = "gpt-oss:latest"


def _resolve_mcp_command() -> list[str]:
    raw_command = os.getenv("MCP_COMMAND", "").strip()
    if raw_command:
        try:
            parsed = shlex.split(raw_command)
        except ValueError as exc:
            raise RuntimeError(f"MCP_COMMAND inválido: {exc}") from exc

        if not parsed:
            raise RuntimeError("MCP_COMMAND vazio")

        return parsed

    repo_root = Path(__file__).resolve().parents[3]
    entry = repo_root / "apps" / "mcp-server" / "dist" / "main.js"
    return ["node", str(entry), "--transport", "stdio"]


def _call_mcp_ask_code(
    *,
    question: str,
    top_k: int,
    min_score: float,
    llm_model: str,
    ext: str | None,
    content_type: str,
    strict: bool,
    scope_payload: dict[str, object],
    timeout_sec: float,
) -> dict[str, object]:
    command = _resolve_mcp_command()

    input_payload: dict[str, object] = {
        "query": question,
        "topK": top_k,
        "minScore": min_score,
        "llmModel": llm_model,
    }
    if ext:
        input_payload["language"] = ext
    input_payload["contentType"] = content_type
    input_payload["strict"] = strict
    input_payload.update(scope_payload)

    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_notif = {"jsonrpc": "2.0", "method": "initialized"}
    call_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "ask_code", "arguments": input_payload},
    }

    process = subprocess.run(
        command,
        input="\n".join(
            (
                json.dumps(init_req, ensure_ascii=False),
                json.dumps(init_notif, ensure_ascii=False),
                json.dumps(call_req, ensure_ascii=False),
                "",
            )
        ),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )

    stdout_lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]

    if not stdout_lines:
        stderr_message = process.stderr.strip() or "sem detalhes"
        raise RuntimeError(
            f"MCP ask_code não retornou resposta (exit={process.returncode}): {stderr_message}"
        )

    parsed = None
    parsed_error: Exception | None = None
    for line in stdout_lines:
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError as exc:
            parsed_error = exc
            continue

        if not isinstance(candidate, dict):
            continue

        if candidate.get("id") == 2:
            parsed = candidate
            break

    if parsed is None:
        if parsed_error:
            raise RuntimeError("Resposta do MCP inválida") from parsed_error
        raise RuntimeError("Resposta do MCP inválida: resposta tools/call ausente")

    if "error" in parsed:
        error = parsed.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "Erro MCP"))
        else:
            message = "Erro MCP"
        raise RuntimeError(message)

    result = parsed.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Resposta do MCP sem result válido")

    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("Resposta do MCP sem conteúdo")

    first = content[0]
    if not isinstance(first, dict):
        raise RuntimeError("Resposta do MCP sem bloco de conteúdo válido")

    content_text = first.get("text")
    if not isinstance(content_text, str):
        raise RuntimeError("Resposta do MCP sem texto válido")

    try:
        output = json.loads(content_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Resposta do MCP sem JSON válido") from exc

    if not isinstance(output, dict):
        raise RuntimeError("Resposta do MCP sem output válido")

    return output


def _ask_command(args: argparse.Namespace) -> int:
    """
    Comando RAG centralizado no MCP (`ask_code`).
    """
    start_time = perf_counter()
    question = args.question.strip()

    if not question:
        print("Erro: pergunta vazia.", file=sys.stderr)
        return 1

    try:
        llm_model = args.llm_model or os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
        scope_payload = _build_ask_scope_payload(args)

        logger.info(f"Pergunta: {question}")
        logger.info(f"LLM Model: {llm_model}")

        response = _call_mcp_ask_code(
            question=question,
            top_k=args.top_k,
            min_score=args.min_score,
            llm_model=llm_model,
            ext=args.ext,
            content_type=args.content_type,
            strict=bool(args.strict),
            scope_payload=scope_payload,
            timeout_sec=120.0,
        )

        answer = str(response.get("answer", ""))
        evidences = response.get("evidences", [])
        if not isinstance(evidences, list):
            evidences = []

        meta = response.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        elapsed = perf_counter() - start_time
        model_used = str(meta.get("llmModel", llm_model))

        # Output
        if args.json_output:
            output = {
                "question": question,
                "answer": answer,
                "model": model_used,
                "contexts_used": int(meta.get("contextsUsed", len(evidences))),
                "elapsed_sec": round(elapsed, 2),
                "sources": [
                    {
                        "repo": e.get("repo"),
                        "path": e.get("path"),
                        "lines": f"{e.get('startLine')}-{e.get('endLine')}",
                        "score": e.get("score"),
                    }
                    for e in evidences
                    if isinstance(e, dict)
                ],
                "meta": meta,
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"\n💬 **Pergunta:** {question}\n")
            print(f"🤖 **Resposta:**\n{answer}\n")
            
            if args.show_context:
                print("📚 **Fontes consultadas:**")
                for i, evidence in enumerate(evidences, 1):
                    if not isinstance(evidence, dict):
                        continue
                    repo = str(evidence.get("repo", "?"))
                    path = evidence.get("path", "?")
                    lines = f"{evidence.get('startLine', '?')}-{evidence.get('endLine', '?')}"
                    score = float(evidence.get("score", 0.0) or 0.0)
                    print(f"  {i}. [{repo}] {path} (linhas {lines}) - score: {score:.4f}")
                print()
            
            print(f"⏱️  Tempo: {elapsed:.2f}s | Modelo: {model_used}")

        return 0

    except subprocess.TimeoutExpired:
        print("Erro: timeout ao chamar MCP ask_code.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("Erro inesperado")
        print(f"Erro inesperado: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    loaded_env_files = load_env_files()
    if loaded_env_files:
        logger.info(
            "Env files carregados: %s",
            ", ".join(str(path) for path in loaded_env_files),
        )
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        return _scan_command(args)
    if args.command == "chunk":
        return _chunk_command(args)
    if args.command == "init":
        return _init_command(args)
    if args.command == "index":
        return _index_command(args)
    if args.command == "search":
        return _search_command(args)
    if args.command == "ask":
        return _ask_command(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
