from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True)
class SessionTurn:
    id: int
    app_name: str
    environment: str
    tenant_id: str | None
    memory_user_id: str | None
    session_id: str
    role: str
    content: str
    created_at: str
    turn_index: int


class LocalSessionStore:
    """Persistência local do histórico imediato da sessão em SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def append_turn(
        self,
        *,
        app_name: str,
        environment: str,
        tenant_id: str | None,
        memory_user_id: str | None,
        session_id: str,
        role: str,
        content: str,
        turn_index: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_turns(
                  app_name, environment, tenant_id, memory_user_id,
                  session_id, role, content, created_at, turn_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    app_name,
                    environment,
                    tenant_id,
                    memory_user_id,
                    session_id,
                    role,
                    content,
                    _utcnow_iso(),
                    turn_index,
                ],
            )
            conn.commit()

    def load_session_turns(
        self,
        *,
        app_name: str,
        environment: str,
        session_id: str,
        limit: int = 100,
    ) -> list[SessionTurn]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, app_name, environment, tenant_id, memory_user_id,
                       session_id, role, content, created_at, turn_index
                FROM session_turns
                WHERE app_name = ?
                  AND environment = ?
                  AND session_id = ?
                ORDER BY turn_index ASC
                LIMIT ?
                """,
                [app_name, environment, session_id, max(1, limit)],
            ).fetchall()
        return [self._row_to_turn(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_turns (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  app_name TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  tenant_id TEXT,
                  memory_user_id TEXT,
                  session_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  turn_index INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_session_turns_session
                  ON session_turns(app_name, environment, session_id, turn_index);

                CREATE INDEX IF NOT EXISTS idx_session_turns_investigation
                  ON session_turns(app_name, environment, tenant_id, memory_user_id, created_at);
                """
            )
            conn.commit()

    def _row_to_turn(self, row: sqlite3.Row) -> SessionTurn:
        return SessionTurn(
            id=int(row["id"]),
            app_name=str(row["app_name"]),
            environment=str(row["environment"]),
            tenant_id=str(row["tenant_id"]) if row["tenant_id"] is not None else None,
            memory_user_id=(
                str(row["memory_user_id"]) if row["memory_user_id"] is not None else None
            ),
            session_id=str(row["session_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=str(row["created_at"]),
            turn_index=int(row["turn_index"]),
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
