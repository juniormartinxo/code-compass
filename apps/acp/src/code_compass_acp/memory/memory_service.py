from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .conflict_resolver import (
    ConflictResolution,
    classify_conflict,
    lexical_similarity,
)
from .env_utils import env_int
from .local_memory_qdrant_index import LocalMemoryQdrantIndex
from .local_sqlite_store import LocalSQLiteMemoryStore, MemoryEntry
from .memory_decay import calculate_effective_confidence


def build_memory_user_id(tenant_id: str, user_id: str) -> str:
    payload = f"{tenant_id}:{user_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _estimate_tokens(text: str) -> int:
    # Heurística simples para limite de preload.
    return max(1, round(len(text.split()) * 1.15))


@dataclass(frozen=True)
class MemoryContext:
    app_name: str
    environment: str
    tenant_id: str
    user_id: str
    session_id: str
    scope_mode: str
    scope_id: str
    long_term_enabled: bool


class LocalMemoryService:
    def __init__(
        self,
        *,
        store: LocalSQLiteMemoryStore,
        semantic_index: LocalMemoryQdrantIndex | None = None,
    ) -> None:
        self._store = store
        self._semantic_index = semantic_index or LocalMemoryQdrantIndex()

    @property
    def db_path(self) -> Path:
        return self._store.db_path

    def list_entries(
        self,
        *,
        context: MemoryContext,
        include_inactive: bool = True,
        term: str | None = None,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        return self._store.list_entries(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            active_only=not include_inactive,
            term=term,
            limit=limit,
        )

    def preload(self, *, context: MemoryContext) -> list[MemoryEntry]:
        max_entries = max(1, env_int("ACP_PRELOAD_MEMORY_MAX_ENTRIES", 20))
        max_tokens = max(200, env_int("ACP_PRELOAD_MEMORY_MAX_TOKENS", 1500))

        entries = self._store.list_entries(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            active_only=True,
            limit=max(100, max_entries * 5),
        )

        scored: list[tuple[float, datetime, MemoryEntry]] = []
        for entry in entries:
            effective = calculate_effective_confidence(
                confidence=entry.confidence,
                kind=entry.kind,
                created_at=entry.created_at,
                last_confirmed_at=entry.last_confirmed_at,
                times_reinforced=entry.times_reinforced,
            )
            recency = entry.last_confirmed_at or entry.updated_at or entry.created_at
            scored.append((effective, recency, entry))

        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)

        selected: list[MemoryEntry] = []
        used_tokens = 0
        for _, _, entry in scored:
            token_cost = _estimate_tokens(f"{entry.topic}: {entry.value}")
            if selected and used_tokens + token_cost > max_tokens:
                continue
            selected.append(entry)
            used_tokens += token_cost
            if len(selected) >= max_entries:
                break
        return selected

    def forget(self, *, context: MemoryContext, term: str) -> int:
        hits = self._store.list_entries(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            active_only=True,
            term=term,
            limit=200,
        )
        ids = [entry.id for entry in hits]
        updated = self._store.disable_entries(
            ids,
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            reason="manual_forget",
        )
        self._semantic_index.delete_entries(ids)
        return updated

    def clear(self, *, context: MemoryContext) -> int:
        return self._store.clear_entries(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            reason="manual_clear",
        )

    def confirm(self, *, context: MemoryContext, entry_id: str) -> MemoryEntry | None:
        try:
            existing = self._store.get_entry(
                app_name=context.app_name,
                environment=context.environment,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                entry_id=entry_id,
            )
        except KeyError:
            return None
        if not existing.active:
            return existing
        self._store.confirm_entry(
            entry_id=entry_id,
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        return self._store.get_entry(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            entry_id=entry_id,
        )

    def explain(self, *, context: MemoryContext, selector: str) -> list[dict[str, Any]]:
        selector = selector.strip()
        if not selector:
            return []
        if self._looks_like_entry_id(selector):
            try:
                entry = self._store.get_entry(
                    app_name=context.app_name,
                    environment=context.environment,
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    entry_id=selector,
                )
                return [self._serialize(entry)]
            except KeyError:
                return []
        matches = self._store.list_entries(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            active_only=False,
            term=selector,
            limit=20,
        )
        return self._serialize_many(matches)

    def remember(
        self,
        *,
        context: MemoryContext,
        kind: str,
        topic: str,
        value: str,
        confidence: float,
        source_session_id: str | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> MemoryEntry | None:
        if not context.long_term_enabled:
            return None

        active_topic_entries = self._store.list_entries(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            active_only=True,
            term=topic,
            limit=40,
        )
        same_topic = [
            entry
            for entry in active_topic_entries
            if entry.kind == kind and entry.topic.lower() == topic.lower()
        ]

        selected_existing: MemoryEntry | None = None
        selected_resolution = ConflictResolution.INDEPENDENT
        best_similarity = -1.0
        for entry in same_topic:
            similarity = lexical_similarity(entry.value, value)
            resolution = classify_conflict(
                existing_value=entry.value,
                new_value=value,
                similarity=similarity,
            )
            if similarity > best_similarity:
                best_similarity = similarity
                selected_existing = entry
                selected_resolution = resolution

        if selected_existing is not None and selected_resolution == ConflictResolution.REINFORCEMENT:
            self._store.confirm_entry(
                entry_id=selected_existing.id,
                app_name=context.app_name,
                environment=context.environment,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
            )
            refreshed = self._store.get_entry(
                app_name=context.app_name,
                environment=context.environment,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                entry_id=selected_existing.id,
            )
            self._semantic_index.upsert_entry(
                entry_id=refreshed.id,
                text=f"{refreshed.topic}: {refreshed.value}",
                metadata={"kind": refreshed.kind, "topic": refreshed.topic},
            )
            return refreshed

        superseded_id: str | None = None
        if selected_existing is not None and selected_resolution == ConflictResolution.CONTRADICTION:
            superseded_id = selected_existing.id
            self._store.supersede_entry(
                old_entry_id=selected_existing.id,
                app_name=context.app_name,
                environment=context.environment,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                reason="semantic_contradiction",
            )
            self._semantic_index.delete_entries([selected_existing.id])

        created = self._store.add_entry(
            app_name=context.app_name,
            environment=context.environment,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            scope_mode=context.scope_mode,
            scope_id=context.scope_id,
            kind=kind,
            topic=topic,
            value=value,
            confidence=confidence,
            source_session_id=source_session_id,
            metadata_json=metadata_json,
            supersedes_entry_id=superseded_id,
        )
        self._semantic_index.upsert_entry(
            entry_id=created.id,
            text=f"{created.topic}: {created.value}",
            metadata={"kind": created.kind, "topic": created.topic},
        )
        return created

    def _serialize(self, entry: MemoryEntry) -> dict[str, Any]:
        status = "active"
        if not entry.active:
            is_superseded = self._store.has_superseding_entry(
                app_name=entry.app_name,
                environment=entry.environment,
                tenant_id=entry.tenant_id,
                user_id=entry.user_id,
                entry_id=entry.id,
            )
            status = "superseded" if is_superseded else "disabled"
        return self._serialize_with_status(entry, status=status)

    def _serialize_many(self, entries: list[MemoryEntry]) -> list[dict[str, Any]]:
        if not entries:
            return []
        # Premissa de chamada: todos os entries pertencem ao mesmo app/env/tenant/user.
        # Hoje isso é garantido pelos filtros dos callers (`list_entries`/`explain`).
        first = entries[0]
        identity_key = (first.app_name, first.environment, first.tenant_id, first.user_id)
        assert all(
            (entry.app_name, entry.environment, entry.tenant_id, entry.user_id) == identity_key
            for entry in entries
        ), "serialize_many requer entries no mesmo escopo de isolamento"

        inactive_ids = [entry.id for entry in entries if not entry.active]
        superseded_ids = set()
        if inactive_ids:
            superseded_ids = self._store.find_superseded_entry_ids(
                app_name=first.app_name,
                environment=first.environment,
                tenant_id=first.tenant_id,
                user_id=first.user_id,
                entry_ids=inactive_ids,
            )
        serialized: list[dict[str, Any]] = []
        for entry in entries:
            if entry.active:
                status = "active"
            else:
                status = "superseded" if entry.id in superseded_ids else "disabled"
            serialized.append(self._serialize_with_status(entry, status=status))
        return serialized

    def _serialize_with_status(self, entry: MemoryEntry, *, status: str) -> dict[str, Any]:
        effective = calculate_effective_confidence(
            confidence=entry.confidence,
            kind=entry.kind,
            created_at=entry.created_at,
            last_confirmed_at=entry.last_confirmed_at,
            times_reinforced=entry.times_reinforced,
            now=datetime.now(tz=UTC),
        )
        return {
            "id": entry.id,
            "kind": entry.kind,
            "topic": entry.topic,
            "value": entry.value,
            "confidence": entry.confidence,
            "effective_confidence": round(effective, 4),
            "status": status,
            "source_session_id": entry.source_session_id,
            "times_reinforced": entry.times_reinforced,
            "last_confirmed_at": entry.last_confirmed_at.isoformat()
            if entry.last_confirmed_at
            else None,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }

    def _looks_like_entry_id(self, value: str) -> bool:
        stripped = value.strip()
        return len(stripped) >= 8 and "-" in stripped


class CloudMemoryService:
    """
    Placeholder compatível para `cloud`.

    Enquanto o Memory Bank não estiver acoplado, aplicamos ranking equivalente
    sobre o backend local para manter comportamento previsível em testes.
    """

    def __init__(self, local_delegate: LocalMemoryService) -> None:
        self._local_delegate = local_delegate

    @property
    def db_path(self) -> Path:
        return self._local_delegate.db_path

    def list_entries(self, **kwargs: Any) -> list[MemoryEntry]:
        return self._local_delegate.list_entries(**kwargs)

    def preload(self, **kwargs: Any) -> list[MemoryEntry]:
        return self._local_delegate.preload(**kwargs)

    def forget(self, **kwargs: Any) -> int:
        return self._local_delegate.forget(**kwargs)

    def clear(self, **kwargs: Any) -> int:
        return self._local_delegate.clear(**kwargs)

    def confirm(self, **kwargs: Any) -> MemoryEntry | None:
        return self._local_delegate.confirm(**kwargs)

    def explain(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._local_delegate.explain(**kwargs)

    def remember(self, **kwargs: Any) -> MemoryEntry | None:
        context = kwargs.get("context")
        if isinstance(context, MemoryContext) and (not context.user_id or not context.tenant_id):
            return None
        return self._local_delegate.remember(**kwargs)
