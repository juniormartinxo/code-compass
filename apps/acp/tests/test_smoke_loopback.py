from __future__ import annotations

import asyncio
import json

import pytest

acp = pytest.importorskip("acp")


class DummyBridge:
    def __init__(self, *, delay: float = 0.0, fail_with: Exception | None = None) -> None:
        self.delay = delay
        self.fail_with = fail_with
        self.aborted = False

    async def start(self) -> None:  # pragma: no cover - interface parity
        return

    async def ask_code(
        self, arguments: dict[str, object], cancel_event: asyncio.Event
    ) -> dict[str, object]:
        if self.fail_with is not None:
            raise self.fail_with
        if self.delay:
            await asyncio.sleep(self.delay)
        if cancel_event.is_set():
            raise asyncio.CancelledError()
        return {"answer": f"Resposta para {arguments.get('query', '')}"}

    async def abort(self) -> None:
        self.aborted = True

    async def close(self) -> None:
        return


class DummyConn:
    def __init__(self) -> None:
        self.updates: list[tuple[str, str]] = []

    async def session_update(self, session_id: str, update: object) -> None:
        content = getattr(update, "content", None)
        text = getattr(content, "text", None) if content is not None else None
        if not isinstance(text, str):
            fallback = getattr(update, "text", "")
            text = fallback if isinstance(fallback, str) else ""
        self.updates.append((session_id, text))


def test_prompt_receives_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("Pergunta")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert conn.updates

    asyncio.run(run())


def test_cancel_during_mcp_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge(delay=0.2)
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])

        async def do_prompt() -> acp.PromptResponse:
            return await agent.prompt(
                acp.PromptRequest(
                    prompt=[acp.text_block("Pergunta")],
                    session_id=session.session_id,
                )
            )

        task = asyncio.create_task(do_prompt())
        await asyncio.sleep(0.05)
        await agent.cancel(session_id=session.session_id)
        response = await task

        assert response.stop_reason == "cancelled"
        assert dummy.aborted

    asyncio.run(run())


def test_prompt_surfaces_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge(fail_with=RuntimeError("falha de teste"))
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("Pergunta")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert conn.updates
        assert any("Falha ao consultar o MCP." in text for _, text in conn.updates)
        assert any("falha de teste" in text for _, text in conn.updates)

    asyncio.run(run())


def test_repo_command_accepts_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def fake_repo_exists(repo: str) -> bool:
        return repo in {"golyzer", "cfi", "ui", "base"}

    monkeypatch.setattr(agent_mod, "_repo_exists", fake_repo_exists)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/repo golyzer,cfi,ui,base")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].repo_override == "golyzer,cfi,ui,base"
        assert any(
            "Repos atualizados para: golyzer,cfi,ui,base" in text
            for _, text in conn.updates
        )

    asyncio.run(run())


def test_repo_command_rejects_csv_with_unknown_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def fake_repo_exists(repo: str) -> bool:
        return repo in {"golyzer", "cfi"}

    monkeypatch.setattr(agent_mod, "_repo_exists", fake_repo_exists)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/repo golyzer,cfi,ui")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].repo_override is None
        assert any("Repo 'ui' não existe." in text for _, text in conn.updates)

    asyncio.run(run())


def test_repo_command_keeps_single_repo_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def fake_repo_exists(repo: str) -> bool:
        return repo == "golyzer"

    monkeypatch.setattr(agent_mod, "_repo_exists", fake_repo_exists)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/repo golyzer")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].repo_override == "golyzer"
        assert any("Repo atualizado para: golyzer" in text for _, text in conn.updates)

    asyncio.run(run())


def test_config_command_reports_effective_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)
    monkeypatch.setenv("ACP_REPO", "golyzer,cfi")
    monkeypatch.setenv("LLM_MODEL", "gpt-5-mini")
    monkeypatch.setenv("ACP_PATH_PREFIX", "apps/")
    monkeypatch.setenv("ACP_LANGUAGE", "ts")
    monkeypatch.setenv("ACP_TOPK", "15")
    monkeypatch.setenv("ACP_MIN_SCORE", "0.62")
    monkeypatch.setenv("ACP_GROUNDED", "true")
    monkeypatch.setenv("ACP_CONTENT_TYPE", "docs")
    monkeypatch.setenv("ACP_STRICT", "yes")
    monkeypatch.setenv("ACP_SHOW_META", "1")
    monkeypatch.setenv("ACP_SHOW_CONTEXT", "on")
    monkeypatch.setenv("CODEBASE_ROOT", "/tmp/code-base")

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert conn.updates
        _, text = conn.updates[-1]
        assert text.startswith("Config atual:\n")
        payload = json.loads(text.split("Config atual:\n", maxsplit=1)[1])
        assert payload["scope"] == {"type": "repos", "repos": ["golyzer", "cfi"]}
        assert payload["model"]["active"] == "gpt-5-mini"
        assert payload["filters"]["pathPrefix"] == "apps/"
        assert payload["filters"]["language"] == "ts"
        assert payload["filters"]["topK"] == 15
        assert payload["filters"]["minScore"] == 0.62
        assert payload["filters"]["contentType"] == "docs"
        assert payload["filters"]["grounded"] is True
        assert payload["filters"]["strict"] is True
        assert payload["passthrough"]["showMeta"] is True
        assert payload["passthrough"]["showContext"] is True
        assert payload["codebaseRoot"] == "/tmp/code-base"
        assert payload["askCodePayloadPreview"]["scope"] == {
            "type": "repos",
            "repos": ["golyzer", "cfi"],
        }

    asyncio.run(run())


def test_config_command_reflects_runtime_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def fake_repo_exists(repo: str) -> bool:
        return repo == "base"

    monkeypatch.setattr(agent_mod, "_repo_exists", fake_repo_exists)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/repo base")],
                session_id=session.session_id,
            )
        )
        await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/model gpt-5")],
                session_id=session.session_id,
            )
        )

        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        _, text = conn.updates[-1]
        payload = json.loads(text.split("Config atual:\n", maxsplit=1)[1])
        assert payload["repo"]["active"] == "base"
        assert payload["repo"]["override"] == "base"
        assert payload["model"]["active"] == "gpt-5"
        assert payload["model"]["override"] == "gpt-5"
        assert payload["askCodePayloadPreview"]["scope"] == {"type": "repo", "repo": "base"}
        assert payload["askCodePayloadPreview"]["llmModel"] == "gpt-5"

    asyncio.run(run())
