from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from time import perf_counter

from .chunk import chunk_file
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


def _build_search_header(payload: dict[str, object]) -> str:
    path = payload.get("path", "?")
    start_line = payload.get("start_line", payload.get("startLine", "?"))
    end_line = payload.get("end_line", payload.get("endLine", "?"))
    return f"{path}:{start_line}-{end_line}"


def _format_search_result_block(
    *,
    index: int,
    score: float,
    payload: dict[str, object],
    vector: object | None = None,
) -> str:
    snippet_raw = payload.get("text")
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
        help="Modelo LLM para resposta (default: env LLM_MODEL ou llama3.2)"
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

            for i, r in enumerate(results, 1):
                payload = r.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}

                block = _format_search_result_block(
                    index=i,
                    score=float(r.get("score", 0.0)),
                    payload=payload,
                    vector=r.get("vector") if args.with_vector else None,
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


DEFAULT_LLM_MODEL = "llama3.2"


def _call_ollama_chat(
    ollama_url: str,
    model: str,
    system_prompt: str,
    user_message: str,
    timeout: float = 120.0,
) -> str:
    """
    Chama o Ollama para gerar uma resposta.
    
    Usa a API /api/chat para conversa.
    """
    import httpx
    
    url = f"{ollama_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
    except httpx.HTTPStatusError as exc:
        raise EmbedderError(f"Erro HTTP ao chamar LLM: {exc.response.status_code}") from exc
    except Exception as exc:
        raise EmbedderError(f"Erro ao chamar LLM: {exc}") from exc


def _build_rag_prompt(question: str, contexts: list[dict]) -> tuple[str, str]:
    """
    Constrói o prompt para RAG.
    
    Returns:
        Tupla (system_prompt, user_message)
    """
    system_prompt = """Você é um assistente especializado em analisar código-fonte.
Responda às perguntas do usuário baseando-se APENAS no contexto fornecido.
Se a informação não estiver no contexto, diga que não encontrou essa informação no código indexado.
Seja conciso e direto. Responda em português brasileiro."""

    # Montar contexto
    context_parts = []
    for i, ctx in enumerate(contexts, 1):
        payload = ctx.get("payload", {})
        path = payload.get("path", "desconhecido")
        lines = f"{payload.get('start_line', '?')}-{payload.get('end_line', '?')}"
        # Buscar o texto do chunk se disponível
        text = payload.get("text", "[conteúdo não disponível]")
        
        context_parts.append(f"### Arquivo {i}: {path} (linhas {lines})\n```\n{text}\n```")
    
    context_text = "\n\n".join(context_parts)
    
    user_message = f"""## Contexto do código-fonte:

{context_text}

## Pergunta:
{question}

## Resposta:"""

    return system_prompt, user_message


def _ask_command(args: argparse.Namespace) -> int:
    """
    Comando RAG: busca contexto e gera resposta via LLM.
    
    1. Gera embedding da pergunta
    2. Busca chunks relevantes no Qdrant
    3. Lê o conteúdo dos chunks
    4. Monta prompt com contexto
    5. Chama LLM para gerar resposta
    """
    import time
    from pathlib import Path
    
    start_time = time.time()
    question = args.question.strip()

    if not question:
        print("Erro: pergunta vazia.", file=sys.stderr)
        return 1
    
    try:
        embedder_config = load_embedder_config()
        qdrant_config = load_qdrant_config()
        
        llm_model = args.llm_model or os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
        ollama_url = embedder_config.ollama_url  # Reusar URL do Ollama

        logger.info(f"Pergunta: {question}")
        logger.info(f"LLM Model: {llm_model}")

        # 1. Gerar embedding da pergunta
        with OllamaEmbedder(embedder_config) as embedder:
            vector_size = embedder.probe_vector_size()
            embeddings = embedder.embed_texts([question])
            query_vector = embeddings[0]

        # 2. Buscar chunks relevantes
        with QdrantStore(qdrant_config) as store:
            collection_name = store.resolve_collection_name(
                vector_size=vector_size,
                model_name=embedder_config.model,
            )

            filters = {}
            if hasattr(args, "ext") and args.ext:
                filters["ext"] = args.ext

            results = store.search(
                query_vector=query_vector,
                collection_name=collection_name,
                filters=filters if filters else None,
                top_k=args.top_k,
            )

        # Filtrar caminhos irrelevantes para contexto RAG
        results, excluded_paths = _filter_context_results(results)
        if excluded_paths > 0:
            logger.info(f"Ignorados {excluded_paths} chunks de ambientes/cache (venv, __pycache__, etc.)")

        # Filtrar por score mínimo
        original_count = len(results)
        results = [r for r in results if r["score"] >= args.min_score]
        dropped = original_count - len(results)
        
        if dropped > 0:
            logger.info(f"Ignorados {dropped} chunks com score < {args.min_score}")

        if not results:
            print(f"Nenhum contexto relevante encontrado (score >= {args.min_score}).")
            if dropped > 0:
                print(f"Dica: {dropped} resultados foram encontrados mas tinham baixa relevância.")
                print("Tente reformular a pergunta ou reduzir o --min-score.")
            return 0

        logger.info(f"Chunks de contexto encontrados: {len(results)}")

        # 3. Ler conteúdo dos chunks (se tiver repo_root no payload)
        for r in results:
            payload = r.get("payload", {})
            path = payload.get("path")
            repo_root = payload.get("repo_root")
            start_line = payload.get("start_line", 1)
            end_line = payload.get("end_line")
            
            if path and repo_root:
                full_path = Path(repo_root) / path
                if full_path.exists():
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                            chunk_lines = lines[start_line - 1 : end_line] if end_line else lines[start_line - 1:]
                            payload["text"] = "".join(chunk_lines)
                    except Exception as exc:
                        logger.warning(f"Não foi possível ler {full_path}: {exc}")
                        payload["text"] = "[erro ao ler arquivo]"
                else:
                    payload["text"] = "[arquivo não encontrado]"
            else:
                payload["text"] = "[caminho não disponível]"

        # 4. Construir prompt
        system_prompt, user_message = _build_rag_prompt(question, results)

        # 5. Chamar LLM
        logger.info("Chamando LLM...")
        answer = _call_ollama_chat(
            ollama_url=ollama_url,
            model=llm_model,
            system_prompt=system_prompt,
            user_message=user_message,
        )

        elapsed = time.time() - start_time

        # Output
        if args.json_output:
            output = {
                "question": question,
                "answer": answer,
                "model": llm_model,
                "contexts_used": len(results),
                "elapsed_sec": round(elapsed, 2),
                "sources": [
                    {
                        "path": r["payload"].get("path"),
                        "lines": f"{r['payload'].get('start_line')}-{r['payload'].get('end_line')}",
                        "score": r["score"],
                    }
                    for r in results
                ],
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"\n💬 **Pergunta:** {question}\n")
            print(f"🤖 **Resposta:**\n{answer}\n")
            
            if args.show_context:
                print("📚 **Fontes consultadas:**")
                for i, r in enumerate(results, 1):
                    payload = r["payload"]
                    path = payload.get("path", "?")
                    lines = f"{payload.get('start_line', '?')}-{payload.get('end_line', '?')}"
                    print(f"  {i}. {path} (linhas {lines}) - score: {r['score']:.4f}")
                print()
            
            print(f"⏱️  Tempo: {elapsed:.2f}s | Modelo: {llm_model}")

        return 0

    except EmbedderError as exc:
        print(f"Erro no embedder/LLM: {exc}", file=sys.stderr)
        return 1
    except QdrantStoreError as exc:
        print(f"Erro no Qdrant: {exc}", file=sys.stderr)
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
