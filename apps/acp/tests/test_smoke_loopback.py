from __future__ import annotations

import asyncio

import pytest

acp = pytest.importorskip("acp")


class DummyBridge:
    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.aborted = False

    async def start(self) -> None:  # pragma: no cover - interface parity
        return

    async def ask_code(
        self, arguments: dict[str, object], cancel_event: asyncio.Event
    ) -> dict[str, object]:
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
        text = getattr(update, "text", "")
        self.updates.append((session_id, text))


def test_prompt_receives_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".")
        response = await agent.prompt(
            [acp.text_block("Pergunta")],
            session_id=session.session_id,
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

        session = await agent.new_session(cwd=".")

        async def do_prompt() -> acp.PromptResponse:
            return await agent.prompt(
                [acp.text_block("Pergunta")],
                session_id=session.session_id,
            )

        task = asyncio.create_task(do_prompt())
        await asyncio.sleep(0.05)
        await agent.cancel(session_id=session.session_id)
        response = await task

        assert response.stop_reason == "cancelled"
        assert dummy.aborted

    asyncio.run(run())
