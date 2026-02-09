"""Testes para o módulo embedder."""

from __future__ import annotations

import json
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import patch

from indexer.embedder import (
    DEFAULT_EMBEDDING_BACKOFF_BASE_MS,
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MAX_RETRIES,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_OLLAMA_URL,
    EmbedderConfig,
    EmbedderError,
    EmbedderRetryError,
    EmbedderValidationError,
    OllamaEmbedder,
    load_embedder_config,
)


class TestEmbedderConfig(unittest.TestCase):
    """Testes para EmbedderConfig e load_embedder_config."""

    def test_load_embedder_config_defaults(self) -> None:
        """Deve usar valores default quando não há env vars."""
        with patch.dict("os.environ", {}, clear=True):
            config = load_embedder_config()
            self.assertEqual(config.ollama_url, DEFAULT_OLLAMA_URL)
            self.assertEqual(config.model, DEFAULT_EMBEDDING_MODEL)
            self.assertEqual(config.batch_size, DEFAULT_EMBEDDING_BATCH_SIZE)
            self.assertEqual(config.max_retries, DEFAULT_EMBEDDING_MAX_RETRIES)
            self.assertEqual(config.backoff_base_ms, DEFAULT_EMBEDDING_BACKOFF_BASE_MS)

    def test_load_embedder_config_from_env(self) -> None:
        """Deve carregar valores de variáveis de ambiente."""
        env = {
            "OLLAMA_URL": "http://custom:11434",
            "EMBEDDING_MODEL": "custom-model",
            "EMBEDDING_BATCH_SIZE": "32",
            "EMBEDDING_MAX_RETRIES": "10",
            "EMBEDDING_BACKOFF_BASE_MS": "1000",
        }
        with patch.dict("os.environ", env, clear=True):
            config = load_embedder_config()
            self.assertEqual(config.ollama_url, "http://custom:11434")
            self.assertEqual(config.model, "custom-model")
            self.assertEqual(config.batch_size, 32)
            self.assertEqual(config.max_retries, 10)
            self.assertEqual(config.backoff_base_ms, 1000)

    def test_load_embedder_config_from_args(self) -> None:
        """Args devem ter precedência sobre env vars."""
        env = {"OLLAMA_URL": "http://env:11434"}
        with patch.dict("os.environ", env, clear=True):
            config = load_embedder_config(ollama_url="http://arg:11434")
            self.assertEqual(config.ollama_url, "http://arg:11434")


class MockOllamaHandler(BaseHTTPRequestHandler):
    """Handler HTTP para mock do Ollama."""

    vector_size = 3584
    fail_count = 0
    max_fails = 0

    def log_message(self, *args) -> None:
        pass  # Silenciar logs

    def do_POST(self) -> None:
        if self.path == "/api/embed":
            # Simular falhas temporárias
            if MockOllamaHandler.fail_count < MockOllamaHandler.max_fails:
                MockOllamaHandler.fail_count += 1
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Temporary failure")
                return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            inputs = data.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]

            # Gerar embeddings fake
            embeddings = [
                [0.1] * MockOllamaHandler.vector_size for _ in inputs
            ]

            response = {"embeddings": embeddings}
            response_body = json.dumps(response).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)
        else:
            self.send_response(404)
            self.end_headers()


class TestOllamaEmbedder(unittest.TestCase):
    """Testes para OllamaEmbedder."""

    @classmethod
    def setUpClass(cls) -> None:
        """Iniciar servidor mock."""
        MockOllamaHandler.fail_count = 0
        MockOllamaHandler.max_fails = 0
        cls.server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        """Parar servidor mock."""
        cls.server.shutdown()

    def setUp(self) -> None:
        """Reset estado do mock."""
        MockOllamaHandler.fail_count = 0
        MockOllamaHandler.max_fails = 0
        MockOllamaHandler.vector_size = 3584

    def _make_config(self) -> EmbedderConfig:
        return EmbedderConfig(
            ollama_url=f"http://127.0.0.1:{self.port}",
            model="test-model",
            batch_size=4,
            max_retries=3,
            backoff_base_ms=10,  # Reduzir para testes rápidos
            timeout_seconds=5,
        )

    def test_probe_vector_size(self) -> None:
        """Deve descobrir o vector size via probe."""
        config = self._make_config()
        with OllamaEmbedder(config) as embedder:
            vector_size = embedder.probe_vector_size()
            self.assertEqual(vector_size, 3584)
            self.assertEqual(embedder.vector_size, 3584)

    def test_embed_texts_single(self) -> None:
        """Deve gerar embedding para um texto."""
        config = self._make_config()
        with OllamaEmbedder(config) as embedder:
            embeddings = embedder.embed_texts(["hello world"])
            self.assertEqual(len(embeddings), 1)
            self.assertEqual(len(embeddings[0]), 3584)

    def test_embed_texts_multiple(self) -> None:
        """Deve gerar embeddings para múltiplos textos."""
        config = self._make_config()
        with OllamaEmbedder(config) as embedder:
            texts = ["text1", "text2", "text3"]
            embeddings = embedder.embed_texts(texts)
            self.assertEqual(len(embeddings), 3)

    def test_embed_texts_empty(self) -> None:
        """Deve retornar lista vazia para input vazio."""
        config = self._make_config()
        with OllamaEmbedder(config) as embedder:
            embeddings = embedder.embed_texts([])
            self.assertEqual(embeddings, [])

    def test_embed_texts_validates_size(self) -> None:
        """Deve validar tamanho do vetor se especificado."""
        config = self._make_config()
        with OllamaEmbedder(config) as embedder:
            # Tamanho correto
            embeddings = embedder.embed_texts(["x"], expected_vector_size=3584)
            self.assertEqual(len(embeddings[0]), 3584)

            # Tamanho incorreto
            with self.assertRaises(EmbedderValidationError):
                embedder.embed_texts(["x"], expected_vector_size=768)

    def test_embed_texts_batched(self) -> None:
        """Deve processar textos em batches."""
        config = self._make_config()  # batch_size=4
        with OllamaEmbedder(config) as embedder:
            texts = [f"text{i}" for i in range(10)]
            embeddings = embedder.embed_texts_batched(texts)
            self.assertEqual(len(embeddings), 10)

    def test_retry_on_5xx(self) -> None:
        """Deve fazer retry em erros 5xx."""
        MockOllamaHandler.max_fails = 2  # Falhar 2x, sucesso na 3ª
        config = self._make_config()
        with OllamaEmbedder(config) as embedder:
            embeddings = embedder.embed_texts(["test"])
            self.assertEqual(len(embeddings), 1)
            self.assertEqual(MockOllamaHandler.fail_count, 2)

    def test_retry_exhausted(self) -> None:
        """Deve lançar EmbedderRetryError após esgotar retries."""
        MockOllamaHandler.max_fails = 10  # Sempre falhar
        config = self._make_config()  # max_retries=3
        with OllamaEmbedder(config) as embedder:
            with self.assertRaises(EmbedderRetryError):
                embedder.embed_texts(["test"])


if __name__ == "__main__":
    unittest.main()
