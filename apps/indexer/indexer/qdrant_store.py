"""Camada de abstração para Qdrant vector store."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)

DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_QDRANT_COLLECTION_BASE = "compass_manutic_nomic_embed"
DEFAULT_QDRANT_DISTANCE = "COSINE"
DEFAULT_QDRANT_UPSERT_BATCH = 64


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


@dataclass(frozen=True)
class QdrantConfig:
    """Configuração do Qdrant."""

    url: str
    api_key: str | None
    collection_base: str
    distance: str
    upsert_batch: int


def load_qdrant_config(
    url: str | None = None,
    api_key: str | None = None,
    collection_base: str | None = None,
    distance: str | None = None,
    upsert_batch: int | None = None,
) -> QdrantConfig:
    """Carrega configuração do Qdrant a partir de args ou variáveis de ambiente."""
    resolved_url = url if url is not None else os.getenv("QDRANT_URL")
    resolved_api_key = api_key if api_key is not None else os.getenv("QDRANT_API_KEY")
    resolved_collection_base = (
        collection_base
        if collection_base is not None
        else os.getenv("QDRANT_COLLECTION_BASE")
    )
    resolved_distance = distance if distance is not None else os.getenv("QDRANT_DISTANCE")

    normalized_url = _normalize_optional_string(resolved_url) or DEFAULT_QDRANT_URL
    normalized_api_key = _normalize_optional_string(resolved_api_key)
    normalized_collection_base = (
        _normalize_optional_string(resolved_collection_base)
        or DEFAULT_QDRANT_COLLECTION_BASE
    )
    normalized_distance = _normalize_optional_string(resolved_distance) or DEFAULT_QDRANT_DISTANCE

    return QdrantConfig(
        url=normalized_url,
        api_key=normalized_api_key,
        collection_base=normalized_collection_base,
        distance=normalized_distance,
        upsert_batch=upsert_batch
        or int(os.getenv("QDRANT_UPSERT_BATCH", str(DEFAULT_QDRANT_UPSERT_BATCH))),
    )


class QdrantStoreError(Exception):
    """Erro genérico do Qdrant store."""


class QdrantCollectionError(QdrantStoreError):
    """Erro relacionado a collection (criação, validação)."""


CONTENT_TYPE_FIELD = "content_type"


def build_qdrant_filter(filters: dict[str, Any] | None) -> models.Filter | None:
    """Converte filtros simples para o formato nativo do Qdrant.

    Nota: para `path_prefix`, usa `MatchText` no campo `path` por ser o
    mecanismo disponível neste cliente. É um filtro textual aproximado,
    não um operador de prefixo estrito.
    """
    if not filters:
        return None

    must_conditions: list[models.Condition] = []

    for key, value in filters.items():
        if value is None:
            continue

        if key == "path_prefix" and isinstance(value, str) and value.strip():
            must_conditions.append(
                models.FieldCondition(
                    key="path",
                    match=models.MatchText(text=value.strip()),
                )
            )
            continue

        if isinstance(value, list):
            must_conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchAny(any=value),
                )
            )
            continue

        must_conditions.append(
            models.FieldCondition(
                key=key,
                match=models.MatchValue(value=value),
            )
        )

    if not must_conditions:
        return None

    return models.Filter(must=must_conditions)


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
    Retorna o stem base da collection.

    `vector_size` e `model_name` são ignorados para manter
    assinatura backward-compatible com chamadas existentes.
    """
    del vector_size
    del model_name
    return collection_base


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
            client_kwargs: dict[str, Any] = {"url": self.config.url}
            if self.config.api_key is not None:
                client_kwargs["api_key"] = self.config.api_key

            self._client = QdrantClient(**client_kwargs)
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
        Resolve o nome base da collection.
        """
        self._collection_name = generate_collection_name(
            self.config.collection_base,
            vector_size,
            model_name,
        )
        return self._collection_name

    def resolve_split_collection_names(
        self,
        vector_size: int,
        model_name: str,
    ) -> dict[str, str]:
        """
        Resolve nomes das collections para code/docs.
        """
        stem = generate_collection_name(
            self.config.collection_base,
            vector_size,
            model_name,
        )

        code_collection = f"{stem}__code"
        docs_collection = f"{stem}__docs"
        return {
            "code": code_collection,
            "docs": docs_collection,
        }

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

    def ensure_payload_keyword_index(
        self,
        collection_name: str,
        field_name: str = CONTENT_TYPE_FIELD,
    ) -> None:
        """
        Garante índice de payload KEYWORD para um campo.

        A operação é idempotente no Qdrant.
        """
        try:
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:
            raise QdrantStoreError(
                f"Erro ao criar índice de payload '{field_name}' na collection '{collection_name}': {exc}"
            ) from exc

    def has_payload_field(
        self,
        collection_name: str,
        field_name: str = CONTENT_TYPE_FIELD,
    ) -> bool:
        """Verifica se campo existe no payload_schema da collection."""
        info = self._get_collection_info(collection_name)
        if info is None:
            return False

        payload_schema = getattr(info, "payload_schema", None)
        if not isinstance(payload_schema, dict):
            return False
        return field_name in payload_schema

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
        with_vector: bool = False,
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

        qdrant_filter = build_qdrant_filter(filters)

        # Usar query_points (API v1.16+)
        try:
            results = self.client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=with_vector,
            )
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                logger.info(f"Collection '{collection}' não encontrada")
                return []
            raise QdrantStoreError(f"Erro ao buscar na collection {collection}: {exc}") from exc
        except Exception as exc:
            raise QdrantStoreError(f"Erro ao buscar na collection {collection}: {exc}") from exc

        response: list[dict[str, Any]] = []
        for point in results.points:
            item: dict[str, Any] = {
                "id": str(point.id),
                "score": point.score,
                "payload": point.payload or {},
            }
            if with_vector:
                item["vector"] = getattr(point, "vector", None)
            response.append(item)

        return response

    def count(self, collection_name: str | None = None) -> int:
        """Retorna contagem de pontos na collection."""
        collection = collection_name or self._collection_name
        if not collection:
            raise QdrantStoreError("Collection name não definido")

        result = self.client.count(collection_name=collection)
        return result.count
