from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from time import perf_counter

from .chunk import chunk_file
from .config import ChunkConfig, ScanConfig, load_chunk_config, load_scan_config
from .embedder import EmbedderError, OllamaEmbedder, load_embedder_config
from .qdrant_store import QdrantStore, QdrantStoreError, load_qdrant_config
from .scan import scan_repo

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
        "-k", "--top-k",
        dest="top_k",
        type=int,
        default=5,
        help="Número de resultados (default: 5)"
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
        embedder_config = load_embedder_config()
        qdrant_config = load_qdrant_config()

        # Gerar embedding da query
        with OllamaEmbedder(embedder_config) as embedder:
            vector_size = embedder.probe_vector_size()
            embeddings = embedder.embed_texts([args.query])
            query_vector = embeddings[0]

        # Buscar no Qdrant
        with QdrantStore(qdrant_config) as store:
            collection_name = store.resolve_collection_name(
                vector_size=vector_size,
                model_name=embedder_config.model,
            )

            # Montar filtros
            filters = {}
            if hasattr(args, "ext") and args.ext:
                filters["ext"] = args.ext
            if hasattr(args, "language") and args.language:
                filters["language"] = args.language

            results = store.search(
                query_vector=query_vector,
                collection_name=collection_name,
                filters=filters if filters else None,
                top_k=args.top_k,
            )

        # Output
        if args.json_output:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"\n🔍 Query: \"{args.query}\"")
            print(f"📊 {len(results)} resultado(s):\n")

            for i, r in enumerate(results, 1):
                payload = r["payload"]
                score = r["score"]
                path = payload.get("path", "?")
                ext = payload.get("ext", "?")
                lines = f"{payload.get('start_line', '?')}-{payload.get('end_line', '?')}"

                print(f"  {i}. [{score:.4f}] {path}")
                print(f"     📍 Linhas: {lines} | Extensão: {ext}")
                print()

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


def main() -> int:
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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
