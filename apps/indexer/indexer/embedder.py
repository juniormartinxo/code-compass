"""Ollama embeddings provider com retry/backoff."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EMBEDDING_MODEL = "manutic/nomic-embed-code"
DEFAULT_EMBEDDING_BATCH_SIZE = 16
DEFAULT_EMBEDDING_MAX_RETRIES = 5
DEFAULT_EMBEDDING_BACKOFF_BASE_MS = 500
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class EmbedderConfig:
    """Configuração do embedder."""

    ollama_url: str
    model: str
    batch_size: int
    max_retries: int
    backoff_base_ms: int
    timeout_seconds: int


def load_embedder_config(
    ollama_url: str | None = None,
    model: str | None = None,
    batch_size: int | None = None,
    max_retries: int | None = None,
    backoff_base_ms: int | None = None,
    timeout_seconds: int | None = None,
) -> EmbedderConfig:
    """Carrega configuração do embedder a partir de args ou variáveis de ambiente."""
    return EmbedderConfig(
        ollama_url=ollama_url or os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL),
        model=model or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        batch_size=batch_size
        or int(os.getenv("EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE))),
        max_retries=max_retries
        or int(os.getenv("EMBEDDING_MAX_RETRIES", str(DEFAULT_EMBEDDING_MAX_RETRIES))),
        backoff_base_ms=backoff_base_ms
        or int(
            os.getenv("EMBEDDING_BACKOFF_BASE_MS", str(DEFAULT_EMBEDDING_BACKOFF_BASE_MS))
        ),
        timeout_seconds=timeout_seconds
        or int(os.getenv("EMBEDDING_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
    )


class EmbedderError(Exception):
    """Erro genérico do embedder."""


class EmbedderRetryError(EmbedderError):
    """Erro após esgotar tentativas de retry."""


class EmbedderValidationError(EmbedderError):
    """Erro de validação de resposta do embedder."""


class OllamaEmbedder:
    """Embedder usando Ollama local via HTTP."""

    def __init__(self, config: EmbedderConfig | None = None) -> None:
        self.config = config or load_embedder_config()
        self._client = httpx.Client(timeout=self.config.timeout_seconds)
        self._vector_size: int | None = None

    def close(self) -> None:
        """Fecha o cliente HTTP."""
        self._client.close()

    def __enter__(self) -> "OllamaEmbedder":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @property
    def embed_url(self) -> str:
        """URL do endpoint de embeddings."""
        return f"{self.config.ollama_url.rstrip('/')}/api/embed"

    @property
    def vector_size(self) -> int | None:
        """Retorna o tamanho do vetor (após probe)."""
        return self._vector_size

    def _backoff_delay(self, attempt: int) -> float:
        """Calcula delay exponencial em segundos."""
        delay_ms = self.config.backoff_base_ms * (2**attempt)
        return delay_ms / 1000.0

    def _should_retry(self, exc: Exception) -> bool:
        """Determina se deve tentar novamente baseado no tipo de erro."""
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.ConnectError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return False

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Faz request ao Ollama e retorna embeddings."""
        payload = {"model": self.config.model, "input": texts}

        response = self._client.post(self.embed_url, json=payload)
        response.raise_for_status()

        data = response.json()
        embeddings = data.get("embeddings", [])

        if len(embeddings) != len(texts):
            raise EmbedderValidationError(
                f"Quantidade de embeddings ({len(embeddings)}) != textos ({len(texts)})"
            )

        return embeddings

    def embed_texts(
        self,
        texts: list[str],
        expected_vector_size: int | None = None,
    ) -> list[list[float]]:
        """
        Gera embeddings para uma lista de textos.

        Args:
            texts: Lista de textos para gerar embeddings.
            expected_vector_size: Tamanho esperado do vetor (opcional, para validação).

        Returns:
            Lista de embeddings (list[float]).

        Raises:
            EmbedderRetryError: Após esgotar tentativas.
            EmbedderValidationError: Se resposta for inválida.
        """
        if not texts:
            return []

        last_error: Exception | None = None

        for attempt in range(self.config.max_retries):
            try:
                embeddings = self._request_embeddings(texts)

                # Validar tamanho do vetor
                if embeddings and expected_vector_size is not None:
                    actual_size = len(embeddings[0])
                    if actual_size != expected_vector_size:
                        raise EmbedderValidationError(
                            f"Tamanho do vetor ({actual_size}) != esperado ({expected_vector_size})"
                        )

                return embeddings

            except Exception as exc:
                last_error = exc
                if not self._should_retry(exc):
                    raise

                if attempt < self.config.max_retries - 1:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        f"Tentativa {attempt + 1}/{self.config.max_retries} falhou: {exc}. "
                        f"Aguardando {delay:.2f}s..."
                    )
                    time.sleep(delay)

        raise EmbedderRetryError(
            f"Falha após {self.config.max_retries} tentativas: {last_error}"
        ) from last_error

    def embed_texts_batched(
        self,
        texts: list[str],
        expected_vector_size: int | None = None,
    ) -> list[list[float]]:
        """
        Gera embeddings em batches respeitando batch_size.

        Args:
            texts: Lista de textos para gerar embeddings.
            expected_vector_size: Tamanho esperado do vetor (opcional).

        Returns:
            Lista de embeddings.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        batch_size = self.config.batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = self.embed_texts(batch, expected_vector_size)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def probe_vector_size(self) -> int:
        """
        Descobre o tamanho do vetor do modelo fazendo um embedding de teste.

        Returns:
            Tamanho do vetor (int).

        Raises:
            EmbedderError: Se não conseguir obter o tamanho.
        """
        try:
            embeddings = self.embed_texts(["x"])
            if not embeddings or not embeddings[0]:
                raise EmbedderError("Resposta vazia do Ollama ao probing")

            self._vector_size = len(embeddings[0])
            logger.info(
                f"Vetor size descoberto: {self._vector_size} "
                f"(modelo: {self.config.model})"
            )
            return self._vector_size

        except Exception as exc:
            raise EmbedderError(f"Falha ao obter vector size: {exc}") from exc
