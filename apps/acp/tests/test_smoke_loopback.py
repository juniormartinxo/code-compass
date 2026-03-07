from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

acp = pytest.importorskip("acp")


class DummyBridge:
    def __init__(self, *, delay: float = 0.0, fail_with: Exception | None = None) -> None:
        self.delay = delay
        self.fail_with = fail_with
        self.aborted = False
        self.calls: list[dict[str, object]] = []

    async def start(self) -> None:  # pragma: no cover - interface parity
        return

    async def ask_code(
        self, arguments: dict[str, object], cancel_event: asyncio.Event
    ) -> dict[str, object]:
        self.calls.append(dict(arguments))
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
        self.raw_updates: list[tuple[str, object]] = []

    async def session_update(self, session_id: str, update: object) -> None:
        self.raw_updates.append((session_id, update))
        content = getattr(update, "content", None)
        text = getattr(content, "text", None) if content is not None else None
        if not isinstance(text, str):
            fallback = getattr(update, "text", "")
            text = fallback if isinstance(fallback, str) else ""
        self.updates.append((session_id, text))


def _extract_config_payload(text: str) -> dict[str, object]:
    marker = "Config atual:\n"
    assert text.startswith(marker)
    payload_text = text[len(marker) :].strip()

    if payload_text.startswith("```"):
        lines = payload_text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            payload_text = "\n".join(lines[1:-1])

    return json.loads(payload_text)


def test_build_runtime_adapter_bridge_compat_with_minimal_signature() -> None:
    from code_compass_acp.adk_agent_builder import build_runtime_adapter
    from code_compass_acp.adk_runtime import LegacyRuntimeAdapter

    calls: list[str | None] = []

    def legacy_bridge(llm_model: str | None = None) -> DummyBridge:
        calls.append(llm_model)
        return DummyBridge()

    result = build_runtime_adapter(
        {
            "model": "gpt-5-mini",
            "provider": "openai",
            "api_url": "https://api.example.com",
            "api_key": "token",
        },
        build_bridge_fn=legacy_bridge,
    )
    assert calls == ["gpt-5-mini"]
    assert isinstance(result.adapter, LegacyRuntimeAdapter)


def test_build_runtime_adapter_does_not_swallow_internal_type_error() -> None:
    from code_compass_acp.adk_agent_builder import build_runtime_adapter

    def broken_bridge(**kwargs: object) -> DummyBridge:
        _ = kwargs
        raise TypeError("internal type error")

    with pytest.raises(TypeError, match="internal type error"):
        build_runtime_adapter(
            {
                "model": "gpt-5-mini",
                "provider": "openai",
                "api_url": "https://api.example.com",
                "api_key": "token",
            },
            build_bridge_fn=broken_bridge,
        )


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


def test_prompt_preserves_conversation_context_between_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])

        first = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("Meu nome é Junior.")],
                session_id=session.session_id,
            )
        )
        assert first.stop_reason == "end_turn"

        second = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("Qual é o meu nome?")],
                session_id=session.session_id,
            )
        )
        assert second.stop_reason == "end_turn"

        assert len(dummy.calls) >= 2
        second_call = dummy.calls[1]
        assert second_call.get("query") == "Qual é o meu nome?"
        conversation_context = second_call.get("conversationContext")
        assert isinstance(conversation_context, str)
        assert "Meu nome é Junior." in conversation_context
        assert "Resposta para Meu nome é Junior." in conversation_context

    asyncio.run(run())


def test_new_session_announces_available_slash_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])

        command_update = None
        for update_session_id, update in conn.raw_updates:
            if update_session_id != session.session_id:
                continue
            if getattr(update, "session_update", "") == "available_commands_update":
                command_update = update
                break

        assert command_update is not None

        available_commands = getattr(command_update, "available_commands", [])
        names = {command.name for command in available_commands}
        assert names == {
            "repo",
            "config",
            "model",
            "grounded",
            "knowledge",
            "content-type",
            "memory",
        }

        hints_by_name = {
            command.name: (
                command.input.root.hint
                if command.input is not None
                else None
            )
            for command in available_commands
        }
        assert hints_by_name["repo"] == "<repo[,repo2,...]>"
        assert hints_by_name["config"] is None
        assert hints_by_name["model"] == "<model|perfil|reset>"
        assert hints_by_name["grounded"] == "<on|off|reset>"
        assert hints_by_name["knowledge"] == "<strict|all|reset>"
        assert hints_by_name["content-type"] == "<code|docs|all|reset>"
        assert (
            hints_by_name["memory"]
            == "<list|forget <termo>|clear|enable|disable|why <id|termo>|confirm <id>>"
        )

    asyncio.run(run())


def test_set_config_option_updates_memory_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        await agent.set_config_option(
            config_id="user.id",
            session_id=session.session_id,
            value="junior",
        )
        await agent.set_config_option(
            config_id="user.tenant",
            session_id=session.session_id,
            value="acme",
        )
        await agent.set_config_option(
            config_id="memory.scope.mode",
            session_id=session.session_id,
            value="session",
        )
        response = await agent.set_config_option(
            config_id="memory.long_term.enabled",
            session_id=session.session_id,
            value="false",
        )

        assert response.config_options
        state = agent._sessions[session.session_id]
        assert state.user_id_override == "junior"
        assert state.tenant_id_override == "acme"
        assert state.memory_scope_mode_override == "session"
        assert state.long_term_memory_enabled_override is False

    asyncio.run(run())


def test_memory_command_list_and_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)
    monkeypatch.setenv("ACP_SESSION_BACKEND", "memory")

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        await agent.set_config_option(
            config_id="user.id",
            session_id=session.session_id,
            value="junior",
        )
        await agent.set_config_option(
            config_id="user.tenant",
            session_id=session.session_id,
            value="acme",
        )

        first = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("Meu nome é Junior")],
                session_id=session.session_id,
            )
        )
        assert first.stop_reason == "end_turn"

        list_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/memory list")],
                session_id=session.session_id,
            )
        )
        assert list_response.stop_reason == "end_turn"
        assert any("Memórias do escopo atual" in text for _, text in conn.updates)

        disable_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/memory disable")],
                session_id=session.session_id,
            )
        )
        assert disable_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].long_term_memory_enabled_override is False

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
    monkeypatch.setenv("ACP_KNOWLEDGE_MODE", "all")
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
        payload = _extract_config_payload(text)
        assert payload["scope"] == {"type": "repos", "repos": ["golyzer", "cfi"]}
        assert payload["model"]["active"] == "gpt-5-mini"
        assert payload["grounded"]["active"] is True
        assert payload["grounded"]["override"] is None
        assert payload["grounded"]["env"] is True
        assert payload["knowledge"]["active"] == "all"
        assert payload["knowledge"]["override"] is None
        assert payload["knowledge"]["env"] == "all"
        assert payload["contentType"]["active"] == "docs"
        assert payload["contentType"]["override"] is None
        assert payload["contentType"]["env"] == "docs"
        assert payload["filters"]["pathPrefix"] == "apps/"
        assert payload["filters"]["language"] == "ts"
        assert payload["filters"]["topK"] == 15
        assert payload["filters"]["minScore"] == 0.62
        assert payload["filters"]["contentType"] == "docs"
        assert payload["filters"]["grounded"] is True
        assert payload["filters"]["knowledgeMode"] == "all"
        assert payload["filters"]["strict"] is True
        assert payload["passthrough"]["showMeta"] is True
        assert payload["passthrough"]["showContext"] is True
        assert payload["codebaseRoot"] == "/tmp/code-base"
        assert payload["askCodePayloadPreview"]["scope"] == {
            "type": "repos",
            "repos": ["golyzer", "cfi"],
        }
        assert payload["askCodePayloadPreview"]["knowledgeMode"] == "all"

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
        payload = _extract_config_payload(text)
        assert payload["repo"]["active"] == "base"
        assert payload["repo"]["override"] == "base"
        assert payload["model"]["active"] == "gpt-5"
        assert payload["model"]["override"] == "gpt-5"
        assert payload["grounded"]["active"] is False
        assert payload["grounded"]["override"] is None
        assert payload["knowledge"]["active"] == "strict"
        assert payload["knowledge"]["override"] is None
        assert payload["knowledge"]["env"] is None
        assert payload["contentType"]["active"] is None
        assert payload["contentType"]["override"] is None
        assert payload["contentType"]["env"] is None
        assert payload["askCodePayloadPreview"]["scope"] == {"type": "repo", "repo": "base"}
        assert payload["askCodePayloadPreview"]["llmModel"] == "gpt-5"
        assert payload["askCodePayloadPreview"]["knowledgeMode"] == "strict"

    asyncio.run(run())


def test_model_command_uses_profile_from_toml(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from code_compass_acp import agent as agent_mod

    profiles_file = tmp_path / "model-profiles.toml"
    profiles_file.write_text(
        "\n".join(
            [
                "[profiles.deepseek]",
                "model = \"deepseek-reasoner\"",
                "provider = \"deepseek\"",
                "api_url = \"https://api.deepseek.com\"",
                "api_key_env = \"DEEPSEEK_API_KEY\"",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACP_MODEL_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "token-123")

    build_calls: list[dict[str, str | None]] = []

    def fake_build_bridge(
        llm_model: str | None = None,
        llm_provider: str | None = None,
        llm_api_url: str | None = None,
        llm_api_key: str | None = None,
    ) -> DummyBridge:
        build_calls.append(
            {
                "llm_model": llm_model,
                "llm_provider": llm_provider,
                "llm_api_url": llm_api_url,
                "llm_api_key": llm_api_key,
            }
        )
        return DummyBridge()

    monkeypatch.setattr(agent_mod, "build_bridge", fake_build_bridge)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/model profile:deepseek")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert len(build_calls) >= 2
        assert build_calls[-1]["llm_model"] == "deepseek-reasoner"
        assert build_calls[-1]["llm_provider"] == "deepseek"
        assert build_calls[-1]["llm_api_url"] == "https://api.deepseek.com"
        assert build_calls[-1]["llm_api_key"] == "token-123"

        state = agent._sessions[session.session_id]
        assert state.model_override == "deepseek-reasoner"
        assert state.model_profile_override == "deepseek"
        assert state.llm_provider_override == "deepseek"
        assert state.llm_api_url_override == "https://api.deepseek.com"
        assert state.llm_api_key_override == "token-123"
        assert any("Perfil 'deepseek' ativado:" in text for _, text in conn.updates)

        config_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )
        assert config_response.stop_reason == "end_turn"
        _, config_text = conn.updates[-1]
        config_payload = _extract_config_payload(config_text)
        assert config_payload["model"]["active"] == "deepseek-reasoner"
        assert config_payload["model"]["profile"] == "deepseek"
        assert config_payload["model"]["provider"]["active"] == "deepseek"
        assert config_payload["model"]["apiUrl"]["active"] == "https://api.deepseek.com"
        assert config_payload["model"]["apiKey"]["activeConfigured"] is True

    asyncio.run(run())


def test_model_command_reports_profile_loading_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from code_compass_acp import agent as agent_mod

    profiles_file = tmp_path / "model-profiles.toml"
    profiles_file.write_text(
        "\n".join(
            [
                "[profiles.deepseek]",
                "model = ",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACP_MODEL_PROFILES_FILE", str(profiles_file))

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])
        response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/model profile:deepseek")],
                session_id=session.session_id,
            )
        )

        assert response.stop_reason == "end_turn"
        assert any("Falha ao carregar perfis de modelo." in text for _, text in conn.updates)
        state = agent._sessions[session.session_id]
        assert state.model_override is None
        assert state.model_profile_override is None

    asyncio.run(run())


def test_grounded_command_on_off_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)
    monkeypatch.setenv("ACP_GROUNDED", "false")

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])

        show_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/grounded")],
                session_id=session.session_id,
            )
        )
        assert show_response.stop_reason == "end_turn"
        assert any("Grounded atual: off (fonte: env)." in text for _, text in conn.updates)

        on_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/grounded on")],
                session_id=session.session_id,
            )
        )
        assert on_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].grounded_override is True
        assert any("Grounded ativado para esta sessão." in text for _, text in conn.updates)

        config_on_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )
        assert config_on_response.stop_reason == "end_turn"
        _, config_on_text = conn.updates[-1]
        config_on_payload = _extract_config_payload(config_on_text)
        assert config_on_payload["grounded"]["active"] is True
        assert config_on_payload["grounded"]["override"] is True
        assert config_on_payload["filters"]["grounded"] is True
        assert config_on_payload["askCodePayloadPreview"]["grounded"] is True

        off_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/grounded off")],
                session_id=session.session_id,
            )
        )
        assert off_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].grounded_override is False
        assert any("Grounded desativado para esta sessão." in text for _, text in conn.updates)

        config_off_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )
        assert config_off_response.stop_reason == "end_turn"
        _, config_off_text = conn.updates[-1]
        config_off_payload = _extract_config_payload(config_off_text)
        assert config_off_payload["grounded"]["active"] is False
        assert config_off_payload["grounded"]["override"] is False
        assert config_off_payload["filters"]["grounded"] is False
        assert "grounded" not in config_off_payload["askCodePayloadPreview"]

        reset_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/grounded reset")],
                session_id=session.session_id,
            )
        )
        assert reset_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].grounded_override is None
        assert any(
            "Grounded resetado para o valor do ambiente." in text
            for _, text in conn.updates
        )

    asyncio.run(run())


def test_knowledge_command_strict_all_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)
    monkeypatch.setenv("ACP_KNOWLEDGE_MODE", "strict")

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])

        show_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/knowledge")],
                session_id=session.session_id,
            )
        )
        assert show_response.stop_reason == "end_turn"
        assert any("knowledge atual: strict (fonte: env)." in text for _, text in conn.updates)

        all_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/knowledge all")],
                session_id=session.session_id,
            )
        )
        assert all_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].knowledge_mode_override == "all"
        assert any("knowledgeMode atualizado para: all" in text for _, text in conn.updates)

        config_all_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )
        assert config_all_response.stop_reason == "end_turn"
        _, config_all_text = conn.updates[-1]
        config_all_payload = _extract_config_payload(config_all_text)
        assert config_all_payload["knowledge"]["active"] == "all"
        assert config_all_payload["knowledge"]["override"] == "all"
        assert config_all_payload["knowledge"]["env"] == "strict"
        assert config_all_payload["filters"]["knowledgeMode"] == "all"
        assert config_all_payload["askCodePayloadPreview"]["knowledgeMode"] == "all"

        strict_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/knowledge strict")],
                session_id=session.session_id,
            )
        )
        assert strict_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].knowledge_mode_override == "strict"
        assert any("knowledgeMode atualizado para: strict" in text for _, text in conn.updates)

        reset_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/knowledge reset")],
                session_id=session.session_id,
            )
        )
        assert reset_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].knowledge_mode_override is None
        assert any(
            "knowledgeMode resetado para o valor do ambiente." in text
            for _, text in conn.updates
        )

    asyncio.run(run())


def test_content_type_command_set_show_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_compass_acp import agent as agent_mod

    dummy = DummyBridge()
    monkeypatch.setattr(agent_mod, "build_bridge", lambda llm_model=None: dummy)
    monkeypatch.setenv("ACP_CONTENT_TYPE", "docs")

    async def run() -> None:
        agent = agent_mod.CodeCompassAgent()
        conn = DummyConn()
        agent.on_connect(conn)  # type: ignore[arg-type]

        session = await agent.new_session(cwd=".", mcpServers=[])

        show_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/contentType")],
                session_id=session.session_id,
            )
        )
        assert show_response.stop_reason == "end_turn"
        assert any("contentType atual: docs (fonte: env)." in text for _, text in conn.updates)

        set_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/content-type code")],
                session_id=session.session_id,
            )
        )
        assert set_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].content_type_override == "code"
        assert any("contentType atualizado para: code" in text for _, text in conn.updates)

        config_set_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )
        assert config_set_response.stop_reason == "end_turn"
        _, config_set_text = conn.updates[-1]
        config_set_payload = _extract_config_payload(config_set_text)
        assert config_set_payload["contentType"]["active"] == "code"
        assert config_set_payload["contentType"]["override"] == "code"
        assert config_set_payload["contentType"]["env"] == "docs"
        assert config_set_payload["filters"]["contentType"] == "code"
        assert config_set_payload["askCodePayloadPreview"]["contentType"] == "code"

        reset_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/content-type reset")],
                session_id=session.session_id,
            )
        )
        assert reset_response.stop_reason == "end_turn"
        assert agent._sessions[session.session_id].content_type_override is None
        assert any(
            "contentType resetado para o valor do ambiente." in text
            for _, text in conn.updates
        )

        config_reset_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/config")],
                session_id=session.session_id,
            )
        )
        assert config_reset_response.stop_reason == "end_turn"
        _, config_reset_text = conn.updates[-1]
        config_reset_payload = _extract_config_payload(config_reset_text)
        assert config_reset_payload["contentType"]["active"] == "docs"
        assert config_reset_payload["contentType"]["override"] is None
        assert config_reset_payload["contentType"]["env"] == "docs"
        assert config_reset_payload["filters"]["contentType"] == "docs"
        assert config_reset_payload["askCodePayloadPreview"]["contentType"] == "docs"

        invalid_response = await agent.prompt(
            acp.PromptRequest(
                prompt=[acp.text_block("/content-type invalid")],
                session_id=session.session_id,
            )
        )
        assert invalid_response.stop_reason == "end_turn"
        assert any(
            "Valor inválido. Use /content-type code|docs|all|reset." in text
            for _, text in conn.updates
        )

    asyncio.run(run())


def test_memory_why_marks_superseded_status(tmp_path: Path) -> None:
    from code_compass_acp.memory.local_sqlite_store import LocalSQLiteMemoryStore
    from code_compass_acp.memory.memory_service import LocalMemoryService, MemoryContext

    store = LocalSQLiteMemoryStore(tmp_path / "memory.sqlite3")
    service = LocalMemoryService(store=store)
    context = MemoryContext(
        app_name="code-compass",
        environment="test",
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="session-1",
        scope_mode="user",
        scope_id="scope-user-a",
        long_term_enabled=True,
    )

    first = service.remember(
        context=context,
        kind="convention",
        topic="style",
        value="use tabs in code",
        confidence=0.9,
        source_session_id="session-1",
    )
    assert first is not None

    second = service.remember(
        context=context,
        kind="convention",
        topic="style",
        value="nao use tabs in code",
        confidence=0.9,
        source_session_id="session-1",
    )
    assert second is not None
    assert second.id != first.id

    diagnosis = service.explain(context=context, selector=first.id)
    assert diagnosis
    assert diagnosis[0]["status"] == "superseded"


def test_store_confirm_and_disable_enforce_isolation(tmp_path: Path) -> None:
    from code_compass_acp.memory.local_sqlite_store import LocalSQLiteMemoryStore

    store = LocalSQLiteMemoryStore(tmp_path / "memory.sqlite3")
    entry = store.add_entry(
        app_name="code-compass",
        environment="test",
        tenant_id="tenant-a",
        user_id="user-a",
        scope_mode="user",
        scope_id="scope-user-a",
        kind="fact",
        topic="name",
        value="junior",
        confidence=0.9,
        source_session_id="session-1",
    )

    denied_confirm = store.confirm_entry(
        entry_id=entry.id,
        app_name="code-compass",
        environment="test",
        tenant_id="tenant-a",
        user_id="user-b",
    )
    assert denied_confirm == 0

    allowed_confirm = store.confirm_entry(
        entry_id=entry.id,
        app_name="code-compass",
        environment="test",
        tenant_id="tenant-a",
        user_id="user-a",
    )
    assert allowed_confirm == 1

    denied_disable = store.disable_entries(
        [entry.id],
        app_name="code-compass",
        environment="test",
        tenant_id="tenant-a",
        user_id="user-b",
        reason="manual_forget",
    )
    assert denied_disable == 0

    allowed_disable = store.disable_entries(
        [entry.id],
        app_name="code-compass",
        environment="test",
        tenant_id="tenant-a",
        user_id="user-a",
        reason="manual_forget",
    )
    assert allowed_disable == 1
