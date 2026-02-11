from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from .chunk import chunk_file, read_text
from .config import ChunkConfig, ScanConfig, load_chunk_config, load_scan_config
from .env import load_env_files
from .embedder import EmbedderError, OllamaEmbedder, load_embedder_config
from .qdrant_store import QdrantStore, QdrantStoreError, load_qdrant_config
from .scan import scan_repo

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EXCLUDED_CONTEXT_PATH_PARTS: tuple[str, ...] = (
    "/.venv/",
    "/venv/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/.mypy_cache/",
    "/.ruff_cache/",
)

SEARCH_SNIPPET_MAX_CHARS = 300


def _should_exclude_context_path(path: str | None) -> bool:
    if not path:
        return False
    normalized = f"/{path.replace('\\', '/').strip('/')}/".lower()
    return any(marker in normalized for marker in EXCLUDED_CONTEXT_PATH_PARTS)


def _filter_context_results(results: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    filtered: list[dict[str, object]] = []
    excluded = 0

    for result in results:
        payload = result.get("payload", {})
        path = payload.get("path") if isinstance(payload, dict) else None
        if isinstance(path, str) and _should_exclude_context_path(path):
            excluded += 1
            continue
        filtered.append(result)

    return filtered, excluded


def _normalize_snippet(text: str, max_chars: int = SEARCH_SNIPPET_MAX_CHARS) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


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

    repo = getattr(args, "repo", None)
    if repo:
        return {"repo": repo}

    raise ValueError(
        "Erro: informe --repo (compat) ou um escopo (--scope-repo, --scope-repos, --scope-all)"
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
        "--ollama-url", dest="ollama_url", default=None, help="URL do Ollama"
    )
    init_parser.add_argument(
        "--model", dest="model", default=None, help="Modelo de embedding"
    )
    init_parser.add_argument(
        "--qdrant-url", dest="qdrant_url", default=None, help="URL do Qdrant"
    )
    init_parser.add_argument(
        "--collection", dest="collection", default=None, help="Nome da collection"
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
        "--repo",
        dest="repo",
        default=None,
        help="Repo alvo em modo compat (equivale a scope.repo no MCP)",
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
    Inicializa a collection no Qdrant.

    1. Probe vector_size via Ollama
    2. Resolve/gera collection_name
    3. Cria/valida collection no Qdrant
    """
    try:
        # Carregar configs
        embedder_config = load_embedder_config(
            ollama_url=args.ollama_url,
            model=args.model,
        )
        qdrant_config = load_qdrant_config(
            url=args.qdrant_url,
            collection=args.collection,
        )

        logger.info(f"Conectando ao Ollama: {embedder_config.ollama_url}")
        logger.info(f"Modelo de embedding: {embedder_config.model}")

        # Descobrir vector_size via probe
        with OllamaEmbedder(embedder_config) as embedder:
            vector_size = embedder.probe_vector_size()
            logger.info(f"Vector size descoberto: {vector_size}")

        # Conectar ao Qdrant e garantir collection
        with QdrantStore(qdrant_config) as store:
            collection_name = store.resolve_collection_name(
                vector_size=vector_size,
                model_name=embedder_config.model,
            )
            logger.info(f"Collection name: {collection_name}")

            result = store.ensure_collection(
                collection_name=collection_name,
                vector_size=vector_size,
            )

        # Output JSON
        output = {
            "provider": "ollama",
            "ollama_url": embedder_config.ollama_url,
            "model": embedder_config.model,
            "vector_size": vector_size,
            "collection_name": collection_name,
            "distance": qdrant_config.distance,
            "qdrant_url": qdrant_config.url,
            "action": result["action"],
        }

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
        # Configs
        scan_config = _resolve_scan_config(args)
        chunk_config = _resolve_chunk_config(args)
        embedder_config = load_embedder_config()
        qdrant_config = load_qdrant_config()

        if not scan_config.repo_root.exists() or not scan_config.repo_root.is_dir():
            print(
                f"Erro: REPO_ROOT inválido ou inexistente: {scan_config.repo_root}",
                file=sys.stderr,
            )
            return 1

        logger.info(f"Repo root: {scan_config.repo_root}")
        logger.info(f"Conectando ao Ollama: {embedder_config.ollama_url}")
        logger.info(f"Modelo: {embedder_config.model}")

        # 1. Probe vector_size e preparar collection
        with OllamaEmbedder(embedder_config) as embedder:
            vector_size = embedder.probe_vector_size()

        with QdrantStore(qdrant_config) as store:
            collection_name = store.resolve_collection_name(
                vector_size=vector_size,
                model_name=embedder_config.model,
            )
            store.ensure_collection(
                collection_name=collection_name,
                vector_size=vector_size,
            )

        logger.info(f"Collection: {collection_name}")

        # 2. Scan
        logger.info("Iniciando scan...")
        files, scan_stats = scan_repo(
            repo_root=scan_config.repo_root,
            ignore_dirs=scan_config.ignore_dirs,
            allow_exts=scan_config.allow_exts,
            max_files=args.max_files,
        )
        logger.info(f"Arquivos encontrados: {len(files)}")

        # 3. Chunk todos os arquivos
        logger.info("Iniciando chunking...")
        all_chunks: list[dict] = []
        chunk_errors: int = 0

        for file_path in files:
            abs_path = scan_config.repo_root / file_path
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
                    all_chunks.append(chunk)
            except Exception as exc:
                logger.warning(f"Erro ao chunkar {file_path}: {exc}")
                chunk_errors += 1

        logger.info(f"Total de chunks: {len(all_chunks)}")

        if not all_chunks:
            logger.warning("Nenhum chunk gerado. Encerrando.")
            output = {
                "status": "empty",
                "files_scanned": len(files),
                "chunks_total": 0,
                "points_upserted": 0,
                "elapsed_ms": int((perf_counter() - started) * 1000),
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

        # 4. Embed em batches
        logger.info("Iniciando embedding...")
        texts = [c["content"] for c in all_chunks]

        with OllamaEmbedder(embedder_config) as embedder:
            embeddings = embedder.embed_texts_batched(
                texts=texts,
                expected_vector_size=vector_size,
            )

        logger.info(f"Embeddings gerados: {len(embeddings)}")

        # 5. Montar pontos com IDs estáveis e payload rico
        logger.info("Montando pontos para upsert...")
        points: list[dict] = []

        for chunk, embedding in zip(all_chunks, embeddings):
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
                "source": "repo",
                "repo_root": str(scan_config.repo_root),
            }

            points.append({
                "id": point_id,
                "vector": embedding,
                "payload": payload,
            })

        # 6. Upsert no Qdrant
        logger.info("Iniciando upsert no Qdrant...")

        with QdrantStore(qdrant_config) as store:
            store._collection_name = collection_name
            upsert_result = store.upsert(points=points)

        elapsed_ms = int((perf_counter() - started) * 1000)

        # Output
        output = {
            "status": "success",
            "repo_root": str(scan_config.repo_root),
            "collection_name": collection_name,
            "files_scanned": len(files),
            "chunks_total": len(all_chunks),
            "chunk_errors": chunk_errors,
            "embeddings_generated": len(embeddings),
            "points_upserted": upsert_result["points_upserted"],
            "upsert_batches": upsert_result["batches"],
            "vector_size": vector_size,
            "model": embedder_config.model,
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

        embedder_config = load_embedder_config()
        qdrant_config = load_qdrant_config()

        # Gerar embedding da query
        with OllamaEmbedder(embedder_config) as embedder:
            embeddings = embedder.embed_texts([query])
            query_vector = embeddings[0]
            vector_size = len(query_vector)

        # Buscar no Qdrant
        with QdrantStore(qdrant_config) as store:
            collection_name = store.resolve_collection_name(
                vector_size=vector_size,
                model_name=embedder_config.model,
            )

            filters = _build_search_filters(args)

            results = store.search(
                query_vector=query_vector,
                collection_name=collection_name,
                filters=filters,
                top_k=args.top_k,
                with_vector=args.with_vector,
            )

        if not results:
            print(
                f"Nenhum resultado na collection '{collection_name}' "
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
    input_payload.update(scope_payload)

    request = {
        "id": "indexer-ask",
        "tool": "ask_code",
        "input": input_payload,
    }

    process = subprocess.run(
        command,
        input=f"{json.dumps(request, ensure_ascii=False)}\n",
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

    try:
        parsed = json.loads(stdout_lines[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Resposta do MCP inválida: {stdout_lines[0]}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Resposta do MCP inválida: esperado objeto")

    if parsed.get("ok") is not True:
        error = parsed.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "Erro MCP"))
        else:
            message = "Erro MCP"
        raise RuntimeError(message)

    output = parsed.get("output")
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
