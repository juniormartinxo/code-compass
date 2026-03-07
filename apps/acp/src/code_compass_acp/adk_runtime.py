from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from .bridge import McpBridge


class RuntimeAdapter(Protocol):
    async def start(self) -> None: ...

    async def run_async(self, payload: dict[str, Any], cancel_event: Any) -> dict[str, Any]: ...

    async def abort(self) -> None: ...

    async def close(self) -> None: ...


@dataclass
class LegacyRuntimeAdapter:
    bridge: McpBridge

    async def start(self) -> None:
        await self.bridge.start()

    async def run_async(self, payload: dict[str, Any], cancel_event: Any) -> dict[str, Any]:
        return await self.bridge.ask_code(payload, cancel_event)

    async def abort(self) -> None:
        await self.bridge.abort()

    async def close(self) -> None:
        await self.bridge.close()


@dataclass
class AdkRuntimeAdapter:
    runtime_mode: str

    async def start(self) -> None:
        return

    async def run_async(self, payload: dict[str, Any], cancel_event: Any) -> dict[str, Any]:
        _ = (payload, cancel_event)
        raise RuntimeError(
            "Runtime ADK ainda nao acoplado nesta iteracao. "
            "Use ACP_ENGINE=legacy para manter o fluxo atual."
        )

    async def abort(self) -> None:
        return

    async def close(self) -> None:
        return


def resolve_runtime_mode() -> str:
    mode = os.getenv("AGENT_RUNTIME_MODE", "").strip().lower()
    if mode in {"local", "cloud"}:
        return mode
    return "local"


def resolve_engine() -> str:
    engine = os.getenv("ACP_ENGINE", "").strip().lower()
    if engine in {"legacy", "adk"}:
        return engine
    return "legacy"
