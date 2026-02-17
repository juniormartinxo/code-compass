from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

try:  # pragma: no cover - optional import paths
    import acp
except Exception:  # pragma: no cover
    acp = None  # type: ignore


@dataclass
class ToadAcpClient:
    profile: str | None = None
    debug: bool = False
    repo: str | None = None
    path_prefix: str | None = None
    language: str | None = None
    top_k: int | None = None
    min_score: float | None = None
    llm_model: str | None = None
    grounded: bool = False
    show_meta: bool = False
    show_context: bool = False
    chunks: list[str] = field(default_factory=list, init=False)
    last_payload: dict[str, Any] | None = field(default=None, init=False)

    def ask(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if acp is None:
            raise RuntimeError("SDK ACP não disponível. Instale agent-client-protocol.")

        command = os.getenv("ACP_AGENT_CMD", "").strip()
        args = os.getenv("ACP_AGENT_ARGS", "").split()
        if not command:
            repo_root = Path(__file__).resolve().parents[4]
            command = str(repo_root / "apps" / "acp" / ".venv" / "bin" / "code-compass-acp")

        class _Client:
            async def session_update(self, session_id: str, update: object) -> None:
                content = getattr(update, "content", None)
                text = getattr(content, "text", None) if content is not None else None
                if isinstance(text, str):
                    marker = "__ACP_META__"
                    if text.startswith(marker):
                        try:
                            self_parent.last_payload = json.loads(text[len(marker) :])
                        except json.JSONDecodeError:
                            return
                    else:
                        self_parent.chunks.append(text)

        self_parent = self

        async def _run() -> dict[str, Any]:
            env = os.environ.copy()
            if self_parent.repo:
                env["ACP_REPO"] = self_parent.repo
            if self_parent.path_prefix:
                env["ACP_PATH_PREFIX"] = self_parent.path_prefix
            if self_parent.language:
                env["ACP_LANGUAGE"] = self_parent.language
            if self_parent.top_k is not None:
                env["ACP_TOPK"] = str(self_parent.top_k)
            if self_parent.min_score is not None:
                env["ACP_MIN_SCORE"] = str(self_parent.min_score)
            if self_parent.llm_model:
                env["LLM_MODEL"] = self_parent.llm_model
            if self_parent.grounded:
                env["ACP_GROUNDED"] = "true"
            if self_parent.show_meta:
                env["ACP_SHOW_META"] = "true"
            if self_parent.show_context:
                env["ACP_SHOW_CONTEXT"] = "true"
            async with acp.spawn_agent_process(
                lambda _client: _Client(),
                command,
                *args,
                env=env,
            ) as (conn, _proc):
                await conn.initialize(protocol_version=acp.PROTOCOL_VERSION)
                session = await conn.new_session(cwd=os.getcwd())
                if self.profile:
                    await conn.set_session_config_option("profile", self.profile, session_id=session.session_id)

                blocks = [acp.text_block(prompt)]
                response = await conn.prompt(blocks, session_id=session.session_id)
                payload = response.model_dump()
                if self_parent.show_meta or self_parent.show_context:
                    payload["_passthrough"] = self_parent.last_payload
                return payload

        return asyncio.run(_run())
