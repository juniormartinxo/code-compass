"""Testes para o módulo qdrant_store."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from indexer.qdrant_store import (
    DEFAULT_QDRANT_COLLECTION_BASE,
    DEFAULT_QDRANT_DISTANCE,
    DEFAULT_QDRANT_UPSERT_BATCH,
    DEFAULT_QDRANT_URL,
    QdrantCollectionError,
    QdrantConfig,
    QdrantStore,
    QdrantStoreError,
    generate_collection_name,
    load_qdrant_config,
)


class TestQdrantConfig(unittest.TestCase):
    """Testes para QdrantConfig e load_qdrant_config."""

    def test_load_qdrant_config_defaults(self) -> None:
        """Deve usar valores default quando não há env vars."""
        with patch.dict("os.environ", {}, clear=True):
            config = load_qdrant_config()
            self.assertEqual(config.url, DEFAULT_QDRANT_URL)
            self.assertIsNone(config.api_key)
            self.assertEqual(config.collection_base, DEFAULT_QDRANT_COLLECTION_BASE)
            self.assertIsNone(config.collection)
            self.assertEqual(config.distance, DEFAULT_QDRANT_DISTANCE)
            self.assertEqual(config.upsert_batch, DEFAULT_QDRANT_UPSERT_BATCH)

    def test_load_qdrant_config_from_env(self) -> None:
        """Deve carregar valores de variáveis de ambiente."""
        env = {
            "QDRANT_URL": "http://custom:6333",
            "QDRANT_API_KEY": "secret-key",
            "QDRANT_COLLECTION_BASE": "custom_base",
            "QDRANT_COLLECTION": "custom_collection",
            "QDRANT_DISTANCE": "EUCLID",
            "QDRANT_UPSERT_BATCH": "128",
        }
        with patch.dict("os.environ", env, clear=True):
            config = load_qdrant_config()
            self.assertEqual(config.url, "http://custom:6333")
            self.assertEqual(config.api_key, "secret-key")
            self.assertEqual(config.collection_base, "custom_base")
            self.assertEqual(config.collection, "custom_collection")
            self.assertEqual(config.distance, "EUCLID")
            self.assertEqual(config.upsert_batch, 128)


class TestGenerateCollectionName(unittest.TestCase):
    """Testes para generate_collection_name."""

    def test_basic_generation(self) -> None:
        """Deve gerar nome no formato esperado."""
        name = generate_collection_name(
            collection_base="compass",
            vector_size=3584,
            model_name="manutic/nomic-embed-code",
        )
        self.assertEqual(name, "compass__3584__manutic_nomic_embed_code")

    def test_slugifies_model_name(self) -> None:
        """Deve slugificar nome do modelo."""
        name = generate_collection_name(
            collection_base="test",
            vector_size=768,
            model_name="OpenAI/Text-Embedding-3-Large",
        )
        self.assertEqual(name, "test__768__openai_text_embedding_3_large")

    def test_handles_special_chars(self) -> None:
        """Deve remover caracteres especiais."""
        name = generate_collection_name(
            collection_base="base",
            vector_size=1024,
            model_name="model@v1.2.3!",
        )
        self.assertEqual(name, "base__1024__model_v1_2_3")


class TestQdrantStore(unittest.TestCase):
    """Testes para QdrantStore."""

    def _make_config(self) -> QdrantConfig:
        return QdrantConfig(
            url="http://localhost:6333",
            api_key=None,
            collection_base="test",
            collection=None,
            distance="COSINE",
            upsert_batch=10,
        )

    def test_resolve_collection_name_explicit(self) -> None:
        """Deve usar collection explícita se fornecida."""
        config = QdrantConfig(
            url="http://localhost:6333",
            api_key=None,
            collection_base="test",
            collection="explicit_collection",
            distance="COSINE",
            upsert_batch=10,
        )
        store = QdrantStore(config)
        name = store.resolve_collection_name(
            vector_size=3584,
            model_name="some-model",
        )
        self.assertEqual(name, "explicit_collection")

    def test_resolve_collection_name_auto(self) -> None:
        """Deve gerar collection automaticamente se não fornecida."""
        config = self._make_config()
        store = QdrantStore(config)
        name = store.resolve_collection_name(
            vector_size=3584,
            model_name="manutic/nomic-embed-code",
        )
        self.assertEqual(name, "test__3584__manutic_nomic_embed_code")

    @patch("indexer.qdrant_store.QdrantClient")
    def test_ensure_collection_creates_new(self, mock_client_class: MagicMock) -> None:
        """Deve criar collection se não existir."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Simular collection não existente
        from qdrant_client.http.exceptions import UnexpectedResponse

        mock_client.get_collection.side_effect = UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            content=b"",
            headers={},
        )

        config = self._make_config()
        store = QdrantStore(config)

        result = store.ensure_collection(
            collection_name="new_collection",
            vector_size=3584,
        )

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["collection"], "new_collection")
        self.assertEqual(result["vector_size"], 3584)
        mock_client.create_collection.assert_called_once()

    @patch("indexer.qdrant_store.QdrantClient")
    def test_ensure_collection_validates_existing(
        self, mock_client_class: MagicMock
    ) -> None:
        """Deve validar collection existente."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Simular collection existente com size correto
        from qdrant_client.http import models

        mock_info = MagicMock()
        mock_info.config.params.vectors = models.VectorParams(
            size=3584,
            distance=models.Distance.COSINE,
        )
        mock_client.get_collection.return_value = mock_info

        config = self._make_config()
        store = QdrantStore(config)

        result = store.ensure_collection(
            collection_name="existing_collection",
            vector_size=3584,
        )

        self.assertEqual(result["action"], "validated")
        mock_client.create_collection.assert_not_called()

    @patch("indexer.qdrant_store.QdrantClient")
    def test_ensure_collection_fails_on_size_mismatch(
        self, mock_client_class: MagicMock
    ) -> None:
        """Deve falhar se collection existir com size diferente."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Simular collection existente com size diferente
        from qdrant_client.http import models

        mock_info = MagicMock()
        mock_info.config.params.vectors = models.VectorParams(
            size=768,  # Size diferente
            distance=models.Distance.COSINE,
        )
        mock_client.get_collection.return_value = mock_info

        config = self._make_config()
        store = QdrantStore(config)

        with self.assertRaises(QdrantCollectionError) as ctx:
            store.ensure_collection(
                collection_name="mismatched_collection",
                vector_size=3584,
            )

        self.assertIn("768", str(ctx.exception))
        self.assertIn("3584", str(ctx.exception))

    @patch("indexer.qdrant_store.QdrantClient")
    def test_upsert_batches_points(self, mock_client_class: MagicMock) -> None:
        """Deve fazer upsert em batches."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        config = QdrantConfig(
            url="http://localhost:6333",
            api_key=None,
            collection_base="test",
            collection=None,
            distance="COSINE",
            upsert_batch=3,  # Batch pequeno para teste
        )
        store = QdrantStore(config)
        store._collection_name = "test_collection"

        # 10 pontos, batch_size=3 → 4 batches
        points = [
            {
                "id": f"point_{i}",
                "vector": [0.1] * 768,
                "payload": {"idx": i},
            }
            for i in range(10)
        ]

        result = store.upsert(points)

        self.assertEqual(result["points_upserted"], 10)
        self.assertEqual(result["batches"], 4)
        self.assertEqual(mock_client.upsert.call_count, 4)

    @patch("indexer.qdrant_store.QdrantClient")
    def test_search_basic(self, mock_client_class: MagicMock) -> None:
        """Deve buscar vetores similares."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Simular resultado de busca (query_points retorna objeto com .points)
        mock_point = MagicMock()
        mock_point.id = "result_1"
        mock_point.score = 0.95
        mock_point.payload = {"path": "src/main.py"}
        
        mock_query_result = MagicMock()
        mock_query_result.points = [mock_point]
        mock_client.query_points.return_value = mock_query_result

        config = self._make_config()
        store = QdrantStore(config)
        store._collection_name = "test_collection"

        results = store.search(
            query_vector=[0.1] * 768,
            top_k=5,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "result_1")
        self.assertEqual(results[0]["score"], 0.95)
        self.assertEqual(results[0]["payload"]["path"], "src/main.py")


if __name__ == "__main__":
    unittest.main()
