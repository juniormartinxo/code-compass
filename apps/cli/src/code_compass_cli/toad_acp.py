from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional import paths
    import acp
except Exception:  # pragma: no cover
    acp = None  # type: ignore


@dataclass
class ToadAcpClient:
    profile: str | None = None
    debug: bool = False

    def ask(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if acp is None:
            raise RuntimeError("SDK ACP não disponível. Instale agent-client-protocol.")

        command = os.getenv("TOAD_COMMAND", "")
        args = os.getenv("TOAD_ARGS", "").split()
        if not command:
            command = os.getenv("PYTHON_COMMAND", "python")
            args = ["-m", "toad", *args]

        async def _run() -> dict[str, Any]:
            async with acp.spawn_agent_process(lambda _client: None, command, *args) as (conn, _proc):
                await conn.initialize(protocol_version=acp.PROTOCOL_VERSION)
                session = await conn.new_session(cwd=os.getcwd())
                if self.profile:
                    await conn.set_session_config_option("profile", self.profile, session_id=session.session_id)

                blocks = [acp.text_block(prompt)]
                response = await conn.prompt(blocks, session_id=session.session_id)
                return response.model_dump()

        return asyncio.run(_run())
