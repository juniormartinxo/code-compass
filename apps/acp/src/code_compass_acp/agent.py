from __future__ import annotations

import asyncio
import atexit
import json
import os
import signal
import sys
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
            agent_info=None,
        )

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
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

    async def prompt(self, params: acp.PromptRequest) -> acp.PromptResponse:
        session_id = params.session_id
        debug = os.getenv("ACP_DEBUG", "").strip()
        state = self._sessions.get(session_id)
        if debug:
            print(f"ACP prompt: session_id={session_id} state={'ok' if state else 'missing'}", file=sys.stderr)
        if not state:
            return acp.PromptResponse(stop_reason="refusal")

        question = _blocks_to_text(params.prompt)
        if debug:
            print(f"ACP prompt: question_len={len(question)}", file=sys.stderr)
        if not question:
            return acp.PromptResponse(stop_reason="refusal")

        state.cancel_event.clear()

        async with state.prompt_lock:
            try:
                raw_repo = os.getenv("ACP_REPO", "code-compass").strip()
                payload = {
                    "query": question,
                    "repo": raw_repo,
                }
                path_prefix = os.getenv("ACP_PATH_PREFIX", "").strip()
                language = os.getenv("ACP_LANGUAGE", "").strip()
                top_k = os.getenv("ACP_TOPK", "").strip()
                min_score = os.getenv("ACP_MIN_SCORE", "").strip()
                llm_model = os.getenv("LLM_MODEL", "").strip()
                grounded = os.getenv("ACP_GROUNDED", "").strip().lower()

                if "," in raw_repo:
                    repos = [r.strip() for r in raw_repo.split(",") if r.strip()]
                    if repos:
                        payload.pop("repo", None)
                        payload["scope"] = {"type": "repos", "repos": repos}

                if path_prefix:
                    payload["pathPrefix"] = path_prefix
                if language:
                    payload["language"] = language
                if top_k:
                    try:
                        payload["topK"] = int(top_k)
                    except ValueError:
                        pass
                if min_score:
                    try:
                        payload["minScore"] = float(min_score)
                    except ValueError:
                        pass
                if llm_model:
                    payload["llmModel"] = llm_model
                if grounded in {"1", "true", "yes", "on"}:
                    payload["grounded"] = True
                result = await state.mcp_bridge.ask_code(payload, state.cancel_event)
            except asyncio.CancelledError:
                return acp.PromptResponse(stop_reason="cancelled")
            except Exception as exc:
                if state.mcp_bridge:
                    await state.mcp_bridge.close()
                print(f"Erro MCP: {exc}", file=sys.stderr)
                return acp.PromptResponse(stop_reason="refusal")

            answer = str(result.get("answer", ""))
            show_meta = os.getenv("ACP_SHOW_META", "").strip().lower() in {"1", "true", "yes", "on"}
            show_context = os.getenv("ACP_SHOW_CONTEXT", "").strip().lower() in {"1", "true", "yes", "on"}
            if (show_meta or show_context) and self._conn:
                meta_payload: dict[str, Any] = {}
                if show_meta and isinstance(result.get("meta"), dict):
                    meta_payload["meta"] = result.get("meta")
                if show_context and isinstance(result.get("evidences"), list):
                    meta_payload["evidences"] = result.get("evidences")
                if meta_payload:
                    marker = "__ACP_META__"
                    await self._conn.session_update(
                        session_id,
                        acp.update_agent_message_text(f"{marker}{json.dumps(meta_payload, ensure_ascii=False)}"),
                    )
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
