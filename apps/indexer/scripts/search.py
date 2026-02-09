#!/usr/bin/env python3
"""Script para busca semântica na collection do Qdrant."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Adicionar o diretório do indexer ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from indexer.embedder import OllamaEmbedder, load_embedder_config
from indexer.qdrant_store import QdrantStore, load_qdrant_config


def search(
    query: str,
    top_k: int = 10,
    filters: dict | None = None,
) -> list[dict]:
    """
    Executa busca semântica.
    
    Args:
        query: Texto da query
        top_k: Número de resultados
        filters: Filtros opcionais (ex: {"ext": ".py"})
        
    Returns:
        Lista de resultados com score e payload
    """
    embedder_config = load_embedder_config()
    qdrant_config = load_qdrant_config()
    
    # Gerar embedding da query
    with OllamaEmbedder(embedder_config) as embedder:
        vector_size = embedder.probe_vector_size()
        embeddings = embedder.embed_texts([query])
        query_vector = embeddings[0]
    
    # Resolver collection
    with QdrantStore(qdrant_config) as store:
        collection_name = store.resolve_collection_name(
            vector_size=vector_size,
            model_name=embedder_config.model,
        )
        
        results = store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            filters=filters,
            top_k=top_k,
        )
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Busca semântica na collection do Qdrant"
    )
    parser.add_argument("query", help="Texto da busca")
    parser.add_argument(
        "-k", "--top-k",
        type=int,
        default=5,
        help="Número de resultados (default: 5)"
    )
    parser.add_argument(
        "--ext",
        help="Filtrar por extensão (ex: .py)"
    )
    parser.add_argument(
        "--path",
        help="Filtrar por path (contendo)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output em JSON"
    )
    
    args = parser.parse_args()
    
    # Montar filtros
    filters = {}
    if args.ext:
        filters["ext"] = args.ext
    if args.path:
        filters["path"] = args.path
    
    try:
        results = search(
            query=args.query,
            top_k=args.top_k,
            filters=filters if filters else None,
        )
        
        if args.json:
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
        
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
