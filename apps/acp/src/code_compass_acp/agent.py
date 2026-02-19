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

TRUTHY_VALUES = {"1", "true", "yes", "on"}
VALID_CONTENT_TYPES = {"code", "docs", "all"}


@dataclass
class SessionState:
    cancel_event: asyncio.Event
    prompt_lock: asyncio.Lock
    mcp_bridge: McpBridge
    repo_override: str | None = None
    model_override: str | None = None


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
            repo_override=None,
            model_override=None,
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
                command_response = await _handle_config_command(self._conn, session_id, state, question)
                if command_response is not None:
                    return command_response

                command_response = await _handle_repo_command(self._conn, session_id, state, question)
                if command_response is not None:
                    return command_response

                command_response = await _handle_model_command(self._conn, session_id, state, question)
                if command_response is not None:
                    return command_response

                payload = _build_ask_payload(question, state)
                result = await state.mcp_bridge.ask_code(payload, state.cancel_event)
            except asyncio.CancelledError:
                return acp.PromptResponse(stop_reason="cancelled")
            except Exception as exc:
                if state.mcp_bridge:
                    await state.mcp_bridge.close()
                error_message = (
                    "Falha ao consultar o MCP. "
                    f"Detalhe técnico: {exc}"
                )
                print(f"Erro MCP: {exc}", file=sys.stderr)
                await self._send_update(session_id, error_message)
                return acp.PromptResponse(stop_reason="end_turn")

            answer = str(result.get("answer", ""))
            show_meta = _is_truthy(os.getenv("ACP_SHOW_META", ""))
            show_context = _is_truthy(os.getenv("ACP_SHOW_CONTEXT", ""))
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


async def _handle_config_command(
    conn: acp.Client | None,
    session_id: str,
    state: SessionState,
    question: str,
) -> acp.PromptResponse | None:
    text = question.strip()
    if not text.startswith("/config"):
        return None

    config = _build_runtime_config(state)
    reply = f"Config atual:\n{json.dumps(config, ensure_ascii=False, indent=2)}"

    if conn:
        await conn.session_update(session_id, acp.update_agent_message_text(reply))
    return acp.PromptResponse(stop_reason="end_turn")


async def _handle_repo_command(
    conn: acp.Client | None,
    session_id: str,
    state: SessionState,
    question: str,
) -> acp.PromptResponse | None:
    text = question.strip()
    if not text.startswith("/repo"):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        reply = f"Repo atual: {state.repo_override or os.getenv('ACP_REPO', 'code-compass')}"
    else:
        repos = _parse_repos_csv(parts[1])
        if not repos:
            reply = "Nome do repo vazio. Use /repo <nome> ou /repo repo-a,repo-b."
        else:
            missing_repos: list[str] = []
            for repo in repos:
                if not await _repo_exists(repo):
                    missing_repos.append(repo)

            if missing_repos:
                if len(missing_repos) == 1:
                    reply = (
                        f"Repo '{missing_repos[0]}' não existe. "
                        "Use /repo <nome> ou /repo repo-a,repo-b."
                    )
                else:
                    reply = (
                        f"Repos inexistentes: {','.join(missing_repos)}. "
                        "Use /repo <nome> ou /repo repo-a,repo-b."
                    )
            else:
                state.repo_override = ",".join(repos)
                if len(repos) == 1:
                    reply = f"Repo atualizado para: {state.repo_override}"
                else:
                    reply = f"Repos atualizados para: {state.repo_override}"

    if conn:
        await conn.session_update(session_id, acp.update_agent_message_text(reply))
    return acp.PromptResponse(stop_reason="end_turn")


async def _repo_exists(repo: str) -> bool:
    codebase_root = os.getenv("CODEBASE_ROOT", "").strip()
    if not codebase_root:
        return True
    try:
        from pathlib import Path

        repo_path = Path(codebase_root) / repo
        return repo_path.exists() and repo_path.is_dir()
    except Exception:
        return False


def _build_runtime_config(state: SessionState) -> dict[str, Any]:
    payload_preview = _build_ask_payload("<query>", state)
    payload_preview.pop("query", None)

    active_repo = (state.repo_override or os.getenv("ACP_REPO", "code-compass")).strip()
    active_model = (state.model_override or os.getenv("LLM_MODEL", "")).strip()

    return {
        "scope": payload_preview.get("scope"),
        "repo": {
            "active": active_repo,
            "override": state.repo_override,
            "env": os.getenv("ACP_REPO", "code-compass").strip(),
        },
        "model": {
            "active": active_model or None,
            "override": state.model_override,
            "env": os.getenv("LLM_MODEL", "").strip() or None,
        },
        "filters": {
            "pathPrefix": payload_preview.get("pathPrefix"),
            "language": payload_preview.get("language"),
            "topK": payload_preview.get("topK"),
            "minScore": payload_preview.get("minScore"),
            "contentType": payload_preview.get("contentType"),
            "grounded": payload_preview.get("grounded", False),
            "strict": payload_preview.get("strict", False),
        },
        "passthrough": {
            "showMeta": _is_truthy(os.getenv("ACP_SHOW_META", "")),
            "showContext": _is_truthy(os.getenv("ACP_SHOW_CONTEXT", "")),
        },
        "codebaseRoot": os.getenv("CODEBASE_ROOT", "").strip() or None,
        "askCodePayloadPreview": payload_preview,
    }


def _build_ask_payload(question: str, state: SessionState) -> dict[str, Any]:
    raw_repo = (state.repo_override or os.getenv("ACP_REPO", "code-compass")).strip()
    payload: dict[str, Any] = {
        "query": question,
        "scope": _resolve_scope(raw_repo),
    }

    path_prefix = os.getenv("ACP_PATH_PREFIX", "").strip()
    language = os.getenv("ACP_LANGUAGE", "").strip()
    top_k = _parse_int(os.getenv("ACP_TOPK", ""))
    min_score = _parse_float(os.getenv("ACP_MIN_SCORE", ""))
    llm_model = (state.model_override or os.getenv("LLM_MODEL", "")).strip()
    grounded = _is_truthy(os.getenv("ACP_GROUNDED", ""))
    content_type = os.getenv("ACP_CONTENT_TYPE", "").strip().lower()
    strict = _is_truthy(os.getenv("ACP_STRICT", ""))

    if path_prefix:
        payload["pathPrefix"] = path_prefix
    if language:
        payload["language"] = language
    if top_k is not None:
        payload["topK"] = top_k
    if min_score is not None:
        payload["minScore"] = min_score
    if llm_model:
        payload["llmModel"] = llm_model
    if grounded:
        payload["grounded"] = True
    if content_type in VALID_CONTENT_TYPES:
        payload["contentType"] = content_type
    if strict:
        payload["strict"] = True

    return payload


def _resolve_scope(raw_repo: str) -> dict[str, Any]:
    parsed_repos = _parse_repos_csv(raw_repo)
    if len(parsed_repos) == 1:
        return {"type": "repo", "repo": parsed_repos[0]}
    if len(parsed_repos) > 1:
        return {"type": "repos", "repos": parsed_repos}
    return {"type": "repo", "repo": raw_repo}


def _parse_repos_csv(value: str) -> list[str]:
    repos: list[str] = []
    for raw_repo in value.split(","):
        repo = raw_repo.strip()
        if not repo:
            continue
        if repo not in repos:
            repos.append(repo)
    return repos


def _parse_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in TRUTHY_VALUES


async def _handle_model_command(
    conn: acp.Client | None,
    session_id: str,
    state: SessionState,
    question: str,
) -> acp.PromptResponse | None:
    text = question.strip()
    if not text.startswith("/model"):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        reply = f"Modelo atual: {state.model_override or os.getenv('LLM_MODEL', '') or 'default'}"
    else:
        model = parts[1].strip()
        if not model:
            reply = "Nome do modelo vazio. Use /model <nome>."
        elif model.lower() in {"default", "reset"}:
            state.model_override = None
            reply = "Modelo resetado para o default."
        else:
            state.model_override = model
            reply = f"Modelo atualizado para: {state.model_override}"

    if conn:
        await conn.session_update(session_id, acp.update_agent_message_text(reply))
    return acp.PromptResponse(stop_reason="end_turn")


def _random_session_id() -> str:
    return f"session-{os.urandom(6).hex()}"
