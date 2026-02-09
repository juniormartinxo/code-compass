"""Camada de abstração para Qdrant vector store."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)

DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_QDRANT_COLLECTION_BASE = "compass"
DEFAULT_QDRANT_DISTANCE = "COSINE"
DEFAULT_QDRANT_UPSERT_BATCH = 64


@dataclass(frozen=True)
class QdrantConfig:
    """Configuração do Qdrant."""

    url: str
    api_key: str | None
    collection_base: str
    collection: str | None
    distance: str
    upsert_batch: int


def load_qdrant_config(
    url: str | None = None,
    api_key: str | None = None,
    collection_base: str | None = None,
    collection: str | None = None,
    distance: str | None = None,
    upsert_batch: int | None = None,
) -> QdrantConfig:
    """Carrega configuração do Qdrant a partir de args ou variáveis de ambiente."""
    return QdrantConfig(
        url=url or os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL),
        api_key=api_key or os.getenv("QDRANT_API_KEY"),
        collection_base=collection_base
        or os.getenv("QDRANT_COLLECTION_BASE", DEFAULT_QDRANT_COLLECTION_BASE),
        collection=collection or os.getenv("QDRANT_COLLECTION"),
        distance=distance or os.getenv("QDRANT_DISTANCE", DEFAULT_QDRANT_DISTANCE),
        upsert_batch=upsert_batch
        or int(os.getenv("QDRANT_UPSERT_BATCH", str(DEFAULT_QDRANT_UPSERT_BATCH))),
    )


class QdrantStoreError(Exception):
    """Erro genérico do Qdrant store."""


class QdrantCollectionError(QdrantStoreError):
    """Erro relacionado a collection (criação, validação)."""


def _slugify(text: str) -> str:
    """Converte texto para slug (lowercase, underscores)."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def _resolve_distance(distance_str: str) -> models.Distance:
    """Converte string de distância para enum do Qdrant."""
    distance_map = {
        "cosine": models.Distance.COSINE,
        "euclid": models.Distance.EUCLID,
        "dot": models.Distance.DOT,
        "manhattan": models.Distance.MANHATTAN,
    }
    key = distance_str.lower()
    if key not in distance_map:
        valid = ", ".join(distance_map.keys())
        raise QdrantStoreError(f"Distância inválida: {distance_str}. Válidas: {valid}")
    return distance_map[key]


def generate_collection_name(
    collection_base: str,
    vector_size: int,
    model_name: str,
) -> str:
    """
    Gera nome da collection baseado em base, vector_size e modelo.

    Formato: {base}__{vector_size}__{model_slug}
    Ex: compass__3584__manutic_nomic_embed_code
    """
    model_slug = _slugify(model_name)
    return f"{collection_base}__{vector_size}__{model_slug}"


class QdrantStore:
    """Abstração para operações no Qdrant."""

    def __init__(self, config: QdrantConfig | None = None) -> None:
        self.config = config or load_qdrant_config()
        self._client: QdrantClient | None = None
        self._collection_name: str | None = None

    @property
    def client(self) -> QdrantClient:
        """Retorna cliente Qdrant (lazy init)."""
        if self._client is None:
            self._client = QdrantClient(
                url=self.config.url,
                api_key=self.config.api_key,
            )
        return self._client

    @property
    def collection_name(self) -> str | None:
        """Retorna nome da collection atual."""
        return self._collection_name

    def close(self) -> None:
        """Fecha o cliente Qdrant."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "QdrantStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def resolve_collection_name(
        self,
        vector_size: int,
        model_name: str,
    ) -> str:
        """
        Resolve o nome da collection.

        Se QDRANT_COLLECTION estiver definido, usa ele.
        Senão, gera automaticamente baseado em base/size/model.
        """
        if self.config.collection:
            self._collection_name = self.config.collection
        else:
            self._collection_name = generate_collection_name(
                self.config.collection_base,
                vector_size,
                model_name,
            )
        return self._collection_name

    def _collection_exists(self, collection_name: str) -> bool:
        """Verifica se collection existe."""
        try:
            collections = self.client.get_collections()
            return any(c.name == collection_name for c in collections.collections)
        except Exception as exc:
            raise QdrantStoreError(f"Erro ao listar collections: {exc}") from exc

    def _get_collection_info(
        self, collection_name: str
    ) -> models.CollectionInfo | None:
        """Retorna info da collection ou None se não existir."""
        try:
            return self.client.get_collection(collection_name)
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                return None
            raise QdrantStoreError(
                f"Erro ao obter info da collection {collection_name}: {exc}"
            ) from exc
        except Exception as exc:
            raise QdrantStoreError(
                f"Erro ao obter info da collection {collection_name}: {exc}"
            ) from exc

    def ensure_collection(
        self,
        collection_name: str,
        vector_size: int,
    ) -> dict[str, Any]:
        """
        Garante que collection existe com o vector_size correto.

        Se não existir, cria. Se existir, valida tamanho.

        Args:
            collection_name: Nome da collection.
            vector_size: Tamanho esperado do vetor.

        Returns:
            Dict com info da operação.

        Raises:
            QdrantCollectionError: Se collection existir com tamanho diferente.
        """
        self._collection_name = collection_name
        distance = _resolve_distance(self.config.distance)

        info = self._get_collection_info(collection_name)

        if info is None:
            # Collection não existe, criar
            logger.info(f"Criando collection '{collection_name}' com size={vector_size}")
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=distance,
                ),
            )
            return {
                "action": "created",
                "collection": collection_name,
                "vector_size": vector_size,
                "distance": self.config.distance,
            }

        # Collection existe, validar tamanho
        vectors_config = info.config.params.vectors
        if isinstance(vectors_config, models.VectorParams):
            existing_size = vectors_config.size
        else:
            # Named vectors - pegar o default ou primeiro
            existing_size = None
            if hasattr(vectors_config, "get"):
                default_config = vectors_config.get("")
                if default_config:
                    existing_size = default_config.size

        if existing_size is None:
            raise QdrantCollectionError(
                f"Não foi possível determinar vector size da collection '{collection_name}'"
            )

        if existing_size != vector_size:
            raise QdrantCollectionError(
                f"Collection '{collection_name}' tem vector size {existing_size}, "
                f"mas embedding model retorna {vector_size}. "
                f"Use outra collection ou delete a existente."
            )

        logger.info(
            f"Collection '{collection_name}' já existe com size={existing_size} (OK)"
        )
        return {
            "action": "validated",
            "collection": collection_name,
            "vector_size": existing_size,
            "distance": self.config.distance,
        }

    def upsert(
        self,
        points: list[dict[str, Any]],
        collection_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Faz upsert de pontos no Qdrant em batches.

        Args:
            points: Lista de dicts com 'id', 'vector', 'payload'.
            collection_name: Nome da collection (usa default se None).

        Returns:
            Dict com stats do upsert.
        """
        collection = collection_name or self._collection_name
        if not collection:
            raise QdrantStoreError("Collection name não definido")

        if not points:
            return {"points_upserted": 0, "batches": 0}

        batch_size = self.config.upsert_batch
        total_upserted = 0
        batches = 0

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            qdrant_points = [
                models.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p.get("payload", {}),
                )
                for p in batch
            ]

            self.client.upsert(
                collection_name=collection,
                points=qdrant_points,
            )

            total_upserted += len(batch)
            batches += 1
            logger.debug(f"Upsert batch {batches}: {len(batch)} pontos")

        logger.info(f"Total: {total_upserted} pontos em {batches} batches")
        return {"points_upserted": total_upserted, "batches": batches}

    def search(
        self,
        query_vector: list[float],
        collection_name: str | None = None,
        filters: dict[str, Any] | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Busca vetores similares no Qdrant.

        Args:
            query_vector: Vetor de query.
            collection_name: Nome da collection.
            filters: Filtros opcionais (ex: {"path": "src/..."}).
            top_k: Número de resultados.

        Returns:
            Lista de dicts com 'id', 'score', 'payload'.
        """
        collection = collection_name or self._collection_name
        if not collection:
            raise QdrantStoreError("Collection name não definido")

        # Construir filtro Qdrant se fornecido
        qdrant_filter = None
        if filters:
            must_conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchAny(any=value),
                        )
                    )
                else:
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        )
                    )
            if must_conditions:
                qdrant_filter = models.Filter(must=must_conditions)

        # Usar query_points (API v1.16+)
        results = self.client.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                "payload": r.payload or {},
            }
            for r in results.points
        ]

    def count(self, collection_name: str | None = None) -> int:
        """Retorna contagem de pontos na collection."""
        collection = collection_name or self._collection_name
        if not collection:
            raise QdrantStoreError("Collection name não definido")

        result = self.client.count(collection_name=collection)
        return result.count
