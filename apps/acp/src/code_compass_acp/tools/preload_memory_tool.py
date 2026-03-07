from __future__ import annotations

from ..memory.memory_decay import calculate_effective_confidence
from ..memory.memory_service import CloudMemoryService, LocalMemoryService, MemoryContext

def build_memory_preload_block(
    *,
    memory_service: LocalMemoryService | CloudMemoryService,
    context: MemoryContext,
) -> str:
    entries = memory_service.preload(context=context)
    if not entries:
        return ""

    lines = ["[Memória longa relevante]"]
    for entry in entries:
        line = (
            f"- {entry.kind}/{entry.topic}: {entry.value} "
            f"(effective_confidence={calculate_effective_confidence(confidence=entry.confidence, kind=entry.kind, created_at=entry.created_at, last_confirmed_at=entry.last_confirmed_at, times_reinforced=entry.times_reinforced):.2f})"
        )
        lines.append(line)
    return "\n".join(lines)
