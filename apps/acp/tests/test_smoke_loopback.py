from __future__ import annotations

import asyncio

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
