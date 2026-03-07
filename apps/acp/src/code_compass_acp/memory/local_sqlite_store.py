from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _hash_text(value: str) -> str:
    return hashlib.sha256(_normalize_text(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    app_name: str
    environment: str
    tenant_id: str
    user_id: str
    scope_mode: str
    scope_id: str
    kind: str
    topic: str
    value: str
    value_hash: str
    confidence: float
    last_confirmed_at: datetime | None
    times_reinforced: int
    source_session_id: str | None
    active: bool
    supersedes_entry_id: str | None
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None
    disabled_reason: str | None
    metadata_json: dict[str, Any] | None


class LocalSQLiteMemoryStore:
    """Source of truth para memória longa local."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def add_entry(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        scope_mode: str,
        scope_id: str,
        kind: str,
        topic: str,
        value: str,
        confidence: float,
        source_session_id: str | None,
        metadata_json: dict[str, Any] | None = None,
        supersedes_entry_id: str | None = None,
    ) -> MemoryEntry:
        now = _utcnow()
        entry_id = str(uuid4())
        payload = (
            entry_id,
            app_name,
            environment,
            tenant_id,
            user_id,
            scope_mode,
            scope_id,
            kind,
            topic,
            value,
            _hash_text(value),
            float(confidence),
            None,
            0,
            source_session_id,
            1,
            supersedes_entry_id,
            _to_iso(now),
            _to_iso(now),
            None,
            None,
            json.dumps(metadata_json, ensure_ascii=False, sort_keys=True)
            if metadata_json is not None
            else None,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_entries (
                  id, app_name, environment, tenant_id, user_id,
                  scope_mode, scope_id, kind, topic, value, value_hash,
                  confidence, last_confirmed_at, times_reinforced,
                  source_session_id, active, supersedes_entry_id,
                  created_at, updated_at, disabled_at, disabled_reason, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            conn.commit()
        return self.get_entry(
            app_name=app_name,
            environment=environment,
            tenant_id=tenant_id,
            user_id=user_id,
            entry_id=entry_id,
        )

    def list_entries(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        scope_mode: str | None = None,
        scope_id: str | None = None,
        active_only: bool = False,
        term: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        self._validate_scope_filter(app_name, environment, tenant_id, scope_id)
        predicates = [
            "app_name = ?",
            "environment = ?",
            "tenant_id = ?",
            "user_id = ?",
        ]
        params: list[Any] = [app_name, environment, tenant_id, user_id]

        if scope_mode:
            predicates.append("scope_mode = ?")
            params.append(scope_mode)
        if scope_id:
            predicates.append("scope_id = ?")
            params.append(scope_id)
        if active_only:
            predicates.append("active = 1")
        if term:
            pattern = f"%{term.strip().lower()}%"
            predicates.append("(lower(topic) LIKE ? OR lower(value) LIKE ?)")
            params.extend([pattern, pattern])

        sql = (
            "SELECT * FROM memory_entries "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY updated_at DESC "
            "LIMIT ?"
        )
        params.append(max(1, limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_entry(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        entry_id: str,
    ) -> MemoryEntry:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_entries
                WHERE id = ?
                  AND app_name = ?
                  AND environment = ?
                  AND tenant_id = ?
                  AND user_id = ?
                """,
                [entry_id, app_name, environment, tenant_id, user_id],
            ).fetchone()
        if row is None:
            raise KeyError(entry_id)
        return self._row_to_entry(row)

    def disable_entries(
        self,
        entry_ids: list[str],
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        reason: str,
    ) -> int:
        if not entry_ids:
            return 0
        now = _to_iso(_utcnow())
        placeholders = ", ".join(["?"] * len(entry_ids))
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE memory_entries
                SET active = 0,
                    updated_at = ?,
                    disabled_at = COALESCE(disabled_at, ?),
                    disabled_reason = ?
                WHERE app_name = ?
                  AND environment = ?
                  AND tenant_id = ?
                  AND user_id = ?
                  AND id IN ({placeholders})
                  AND active = 1
                """,
                [now, now, reason, app_name, environment, tenant_id, user_id, *entry_ids],
            )
            conn.commit()
        return int(cursor.rowcount or 0)

    def supersede_entry(
        self,
        *,
        old_entry_id: str,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        reason: str,
    ) -> int:
        now = _to_iso(_utcnow())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_entries
                SET active = 0,
                    updated_at = ?,
                    disabled_at = ?,
                    disabled_reason = ?
                WHERE app_name = ?
                  AND environment = ?
                  AND tenant_id = ?
                  AND user_id = ?
                  AND id = ?
                  AND active = 1
                """,
                [now, now, reason, app_name, environment, tenant_id, user_id, old_entry_id],
            )
            conn.commit()
        return int(cursor.rowcount or 0)

    def clear_entries(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        scope_mode: str | None = None,
        scope_id: str | None = None,
        reason: str = "manual_clear",
    ) -> int:
        self._validate_scope_filter(app_name, environment, tenant_id, scope_id)
        now = _to_iso(_utcnow())
        predicates = [
            "app_name = ?",
            "environment = ?",
            "tenant_id = ?",
            "user_id = ?",
            "active = 1",
        ]
        params: list[Any] = [app_name, environment, tenant_id, user_id]
        if scope_mode:
            predicates.append("scope_mode = ?")
            params.append(scope_mode)
        if scope_id:
            predicates.append("scope_id = ?")
            params.append(scope_id)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE memory_entries
                SET active = 0,
                    updated_at = ?,
                    disabled_at = COALESCE(disabled_at, ?),
                    disabled_reason = ?
                WHERE {' AND '.join(predicates)}
                """,
                [now, now, reason, *params],
            )
            conn.commit()
        return int(cursor.rowcount or 0)

    def confirm_entry(
        self,
        *,
        entry_id: str,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
    ) -> int:
        now = _to_iso(_utcnow())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_entries
                SET times_reinforced = times_reinforced + 1,
                    last_confirmed_at = ?,
                    updated_at = ?
                WHERE app_name = ?
                  AND environment = ?
                  AND tenant_id = ?
                  AND user_id = ?
                  AND id = ?
                """,
                [now, now, app_name, environment, tenant_id, user_id, entry_id],
            )
            conn.commit()
        return int(cursor.rowcount or 0)

    def has_superseding_entry(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        entry_id: str,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM memory_entries
                WHERE app_name = ?
                  AND environment = ?
                  AND tenant_id = ?
                  AND user_id = ?
                  AND supersedes_entry_id = ?
                LIMIT 1
                """,
                [app_name, environment, tenant_id, user_id, entry_id],
            ).fetchone()
        return row is not None

    def find_superseded_entry_ids(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str,
        user_id: str,
        entry_ids: list[str],
    ) -> set[str]:
        if not entry_ids:
            return set()
        placeholders = ", ".join(["?"] * len(entry_ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT supersedes_entry_id
                FROM memory_entries
                WHERE app_name = ?
                  AND environment = ?
                  AND tenant_id = ?
                  AND user_id = ?
                  AND supersedes_entry_id IN ({placeholders})
                """,
                [app_name, environment, tenant_id, user_id, *entry_ids],
            ).fetchall()
        return {str(row["supersedes_entry_id"]) for row in rows if row["supersedes_entry_id"] is not None}

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                  id TEXT PRIMARY KEY,
                  app_name TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  tenant_id TEXT NOT NULL,
                  user_id TEXT NOT NULL,
                  scope_mode TEXT NOT NULL CHECK(scope_mode IN ('session', 'user')),
                  scope_id TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  topic TEXT NOT NULL,
                  value TEXT NOT NULL,
                  value_hash TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  last_confirmed_at TEXT,
                  times_reinforced INTEGER NOT NULL DEFAULT 0,
                  source_session_id TEXT,
                  active INTEGER NOT NULL DEFAULT 1,
                  supersedes_entry_id TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  disabled_at TEXT,
                  disabled_reason TEXT,
                  metadata_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_memory_entries_isolation_active
                  ON memory_entries(app_name, environment, tenant_id, user_id, active);

                CREATE INDEX IF NOT EXISTS idx_memory_entries_kind_topic
                  ON memory_entries(app_name, environment, tenant_id, user_id, kind, topic);

                CREATE INDEX IF NOT EXISTS idx_memory_entries_scope
                  ON memory_entries(app_name, environment, tenant_id, scope_mode, scope_id, active);

                CREATE INDEX IF NOT EXISTS idx_memory_entries_updated_at
                  ON memory_entries(updated_at);
                """
            )
            conn.commit()

    def _validate_scope_filter(
        self,
        app_name: str,
        environment: str,
        tenant_id: str,
        scope_id: str | None,
    ) -> None:
        # Guardrail de isolamento: nunca consultar scope_id sem app/env/tenant.
        if scope_id is None:
            return
        if not app_name or not environment or not tenant_id:
            raise ValueError(
                "scope_id exige app_name + environment + tenant_id para evitar colisões."
            )

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        metadata_raw = row["metadata_json"]
        metadata_json: dict[str, Any] | None = None
        if isinstance(metadata_raw, str) and metadata_raw.strip():
            try:
                parsed = json.loads(metadata_raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                metadata_json = parsed

        created_at = _from_iso(row["created_at"]) or _utcnow()
        updated_at = _from_iso(row["updated_at"]) or created_at
        return MemoryEntry(
            id=str(row["id"]),
            app_name=str(row["app_name"]),
            environment=str(row["environment"]),
            tenant_id=str(row["tenant_id"]),
            user_id=str(row["user_id"]),
            scope_mode=str(row["scope_mode"]),
            scope_id=str(row["scope_id"]),
            kind=str(row["kind"]),
            topic=str(row["topic"]),
            value=str(row["value"]),
            value_hash=str(row["value_hash"]),
            confidence=float(row["confidence"]),
            last_confirmed_at=_from_iso(row["last_confirmed_at"]),
            times_reinforced=int(row["times_reinforced"]),
            source_session_id=(
                str(row["source_session_id"]) if row["source_session_id"] is not None else None
            ),
            active=bool(int(row["active"])),
            supersedes_entry_id=(
                str(row["supersedes_entry_id"])
                if row["supersedes_entry_id"] is not None
                else None
            ),
            created_at=created_at,
            updated_at=updated_at,
            disabled_at=_from_iso(row["disabled_at"]),
            disabled_reason=(
                str(row["disabled_reason"]) if row["disabled_reason"] is not None else None
            ),
            metadata_json=metadata_json,
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
