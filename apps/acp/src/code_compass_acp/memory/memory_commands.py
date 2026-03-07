from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from .local_sqlite_store import MemoryEntry
from .memory_service import MemoryContext


class MemoryService(Protocol):
    def list_entries(
        self,
        *,
        context: MemoryContext,
        include_inactive: bool = True,
        term: str | None = None,
        limit: int = 50,
    ) -> list[MemoryEntry]: ...

    def forget(self, *, context: MemoryContext, term: str) -> int: ...

    def clear(self, *, context: MemoryContext) -> int: ...

    def explain(self, *, context: MemoryContext, selector: str) -> list[dict[str, object]]: ...

    def confirm(self, *, context: MemoryContext, entry_id: str) -> MemoryEntry | None: ...


@dataclass(frozen=True)
class MemoryCommandExecution:
    handled: bool
    reply: str | None = None


def execute_memory_command(
    *,
    text: str,
    context: MemoryContext | None,
    memory_service: MemoryService | None,
    set_long_term_enabled: Callable[[bool], None],
) -> MemoryCommandExecution:
    stripped = text.strip()
    if not stripped.startswith("/memory"):
        return MemoryCommandExecution(handled=False)

    if memory_service is None or context is None:
        return MemoryCommandExecution(
            handled=True,
            reply="Memória indisponível nesta sessão.",
        )

    command = stripped.split(maxsplit=2)
    action = command[1].strip().lower() if len(command) >= 2 else "list"
    argument = command[2].strip() if len(command) >= 3 else ""

    if action == "list":
        entries = memory_service.list_entries(
            context=context,
            include_inactive=True,
            limit=40,
        )
        if not entries:
            return MemoryCommandExecution(handled=True, reply="Nenhuma memória encontrada.")
        lines = ["Memórias do escopo atual:"]
        for entry in entries:
            status = "active" if entry.active else "disabled"
            lines.append(
                f"- `{entry.id}` [{status}] {entry.kind}/{entry.topic}: {entry.value}"
            )
        return MemoryCommandExecution(handled=True, reply="\n".join(lines))

    if action == "forget":
        if not argument:
            return MemoryCommandExecution(
                handled=True,
                reply="Uso: /memory forget <termo>",
            )
        removed = memory_service.forget(context=context, term=argument)
        return MemoryCommandExecution(
            handled=True,
            reply=f"{removed} memória(s) desativada(s) para o termo '{argument}'.",
        )

    if action == "clear":
        removed = memory_service.clear(context=context)
        return MemoryCommandExecution(
            handled=True,
            reply=f"{removed} memória(s) longa(s) desativada(s).",
        )

    if action == "enable":
        set_long_term_enabled(True)
        return MemoryCommandExecution(
            handled=True,
            reply="Gravação de memória longa ativada para esta sessão.",
        )

    if action == "disable":
        set_long_term_enabled(False)
        return MemoryCommandExecution(
            handled=True,
            reply="Gravação de memória longa desativada para esta sessão.",
        )

    if action == "why":
        if not argument:
            return MemoryCommandExecution(
                handled=True,
                reply="Uso: /memory why <id|termo>",
            )
        explained = memory_service.explain(context=context, selector=argument)
        if not explained:
            return MemoryCommandExecution(
                handled=True,
                reply=f"Nenhuma memória encontrada para '{argument}'.",
            )
        payload = json.dumps(explained, ensure_ascii=False, indent=2)
        return MemoryCommandExecution(
            handled=True,
            reply=f"Diagnóstico de memória:\n```json\n{payload}\n```",
        )

    if action == "confirm":
        if not argument:
            return MemoryCommandExecution(
                handled=True,
                reply="Uso: /memory confirm <id>",
            )
        entry = memory_service.confirm(context=context, entry_id=argument)
        if entry is None:
            return MemoryCommandExecution(
                handled=True,
                reply=f"Memória '{argument}' não encontrada.",
            )
        return MemoryCommandExecution(
            handled=True,
            reply=(
                f"Memória '{entry.id}' reforçada. "
                f"times_reinforced={entry.times_reinforced}, "
                f"last_confirmed_at={entry.last_confirmed_at.isoformat() if entry.last_confirmed_at else 'n/a'}"
            ),
        )

    return MemoryCommandExecution(
        handled=True,
        reply=(
            "Comando inválido. Use "
            "/memory list|forget <termo>|clear|enable|disable|why <id|termo>|confirm <id>"
        ),
    )
