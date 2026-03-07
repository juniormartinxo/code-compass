from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryIndexConfig:
    enabled: bool
    collection: str

    @classmethod
    def from_env(cls) -> MemoryIndexConfig:
        enabled = os.getenv("ACP_MEMORY_QDRANT_INDEX_ENABLED", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        collection = os.getenv("ACP_MEMORY_QDRANT_COLLECTION", "").strip() or "compass_memory_local"
        return cls(enabled=enabled, collection=collection)


class LocalMemoryQdrantIndex:
    """
    Índice semântico opcional.

    Nesta iteração ele é best-effort e nunca é usado como fonte final de verdade.
    """

    def __init__(self, config: MemoryIndexConfig | None = None) -> None:
        self._config = config or MemoryIndexConfig.from_env()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def collection(self) -> str:
        return self._config.collection

    def upsert_entry(self, *, entry_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        _ = (entry_id, text, metadata)
        # TODO: integração real com qdrant-client quando o rollout semântico for habilitado.

    def delete_entries(self, entry_ids: list[str]) -> None:
        if not self.enabled:
            return
        _ = entry_ids
        # TODO: integração real com qdrant-client.

    def shortlist(self, *, query: str, limit: int = 20) -> list[str]:
        if not self.enabled:
            return []
        _ = (query, limit)
        # TODO: shortlist semântico real.
        return []
