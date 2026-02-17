from __future__ import annotations

import asyncio
import atexit
import os
import signal
from dataclasses import dataclass
from typing import Any

import acp

from .bridge import McpBridge, build_bridge
from .chunker import chunk_by_paragraph


@dataclass
class SessionState:
    cancel_event: asyncio.Event
    prompt_lock: asyncio.Lock
    mcp_bridge: McpBridge


class CodeCompassAgent(acp.Agent):
    def __init__(self) -> None:
        super().__init__()
        self._conn: acp.Client | None = None
        self._sessions: dict[str, SessionState] = {}
        atexit.register(self._cleanup_all_sessions)
        signal.signal(signal.SIGTERM, lambda *_: self._cleanup_all_sessions())

    def on_connect(self, conn: acp.Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any | None = None,
        client_info: Any | None = None,
        **_kwargs: Any,
    ) -> acp.InitializeResponse:
        return acp.InitializeResponse(
            protocol_version=protocol_version,
            agent_info=acp.Implementation(name="code-compass-acp", version="0.1.0"),
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: Any | None = None,
        **_kwargs: Any,
    ) -> acp.NewSessionResponse:
        llm_model = os.getenv("LLM_MODEL", "").strip() or None
        bridge = build_bridge(llm_model=llm_model)
        await bridge.start()

        state = SessionState(
            cancel_event=asyncio.Event(),
            prompt_lock=asyncio.Lock(),
            mcp_bridge=bridge,
        )
        session_id = _random_session_id()
        self._sessions[session_id] = state
        return acp.NewSessionResponse(session_id=session_id)

    async def prompt(
        self,
        prompt: list[acp.TextContentBlock | acp.ImageContentBlock | acp.AudioContentBlock | acp.ResourceContentBlock | acp.EmbeddedResourceContentBlock],
        session_id: str,
        **_kwargs: Any,
    ) -> acp.PromptResponse:
        state = self._sessions.get(session_id)
        if not state:
            return acp.PromptResponse(stop_reason="error", error="Sessão não encontrada")

        question = _blocks_to_text(prompt)
        if not question:
            return acp.PromptResponse(stop_reason="error", error="Pergunta vazia")

        state.cancel_event.clear()

        async with state.prompt_lock:
            try:
                payload = {
                    "query": question,
                    "repo": os.getenv("ACP_REPO", "code-compass"),
                }
                result = await state.mcp_bridge.ask_code(payload, state.cancel_event)
            except asyncio.CancelledError:
                return acp.PromptResponse(stop_reason="cancelled")
            except Exception as exc:
                if state.mcp_bridge:
                    await state.mcp_bridge.close()
                return acp.PromptResponse(stop_reason="error", error=str(exc))

            answer = str(result.get("answer", ""))
            for chunk in chunk_by_paragraph(answer):
                if state.cancel_event.is_set():
                    return acp.PromptResponse(stop_reason="cancelled")
                await self._send_update(session_id, chunk)
                delay = os.getenv("ACP_TEST_SLOW_STREAM", "").strip()
                if delay:
                    try:
                        await asyncio.sleep(float(delay))
                    except ValueError:
                        pass

        return acp.PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **_kwargs: Any) -> None:
        state = self._sessions.get(session_id)
        if not state:
            return

        state.cancel_event.set()
        await state.mcp_bridge.abort()

    async def _send_update(self, session_id: str, chunk: str) -> None:
        if not self._conn:
            return
        await self._conn.session_update(
            session_id,
            acp.update_agent_message_text(chunk),
        )

    def _cleanup_all_sessions(self) -> None:
        for state in self._sessions.values():
            try:
                asyncio.run(state.mcp_bridge.close())
            except RuntimeError:
                pass
        self._sessions.clear()


def _blocks_to_text(
    blocks: list[
        acp.TextContentBlock
        | acp.ImageContentBlock
        | acp.AudioContentBlock
        | acp.ResourceContentBlock
        | acp.EmbeddedResourceContentBlock
    ]
) -> str:
    parts: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


def _random_session_id() -> str:
    return f"session-{os.urandom(6).hex()}"
