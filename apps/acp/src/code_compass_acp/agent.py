from __future__ import annotations

import asyncio
import atexit
import json
import os
import signal
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import acp
from acp.helpers import update_available_commands

from .bridge import McpBridge, build_bridge
from .chunker import chunk_by_paragraph

TRUTHY_VALUES = {"1", "true", "yes", "on"}
VALID_CONTENT_TYPES = {"code", "docs", "all"}
GROUNDED_ON_VALUES = {"on", "true", "1", "yes"}
GROUNDED_OFF_VALUES = {"off", "false", "0", "no"}
MODEL_RESET_VALUES = {"default", "reset"}
MODEL_PROFILES_ENV_KEY = "ACP_MODEL_PROFILES_FILE"
DEFAULT_MODEL_PROFILES_FILE = "model-profiles.toml"
AVAILABLE_SLASH_COMMANDS: tuple[dict[str, Any], ...] = (
    {
        "name": "repo",
        "description": "Alterna o contexto de repositório.",
        "input": {"hint": "<repo[,repo2,...]>"},
    },
    {
        "name": "config",
        "description": "Mostra a configuração atual da sessão ACP.",
    },
    {
        "name": "model",
        "description": "Define modelo/perfil para esta sessão.",
        "input": {"hint": "<model|perfil|reset>"},
    },
    {
        "name": "grounded",
        "description": "Ativa ou desativa o modo grounded nesta sessão.",
        "input": {"hint": "<on|off|reset>"},
    },
    {
        "name": "content-type",
        "description": "Define o contentType da sessão.",
        "input": {"hint": "<code|docs|all|reset>"},
    },
)


@dataclass(frozen=True)
class ModelProfile:
    name: str
    model: str
    provider: str | None = None
    api_url: str | None = None
    api_key: str | None = None


@dataclass
class SessionState:
    cancel_event: asyncio.Event
    prompt_lock: asyncio.Lock
    mcp_bridge: McpBridge
    repo_override: str | None = None
    model_override: str | None = None
    model_profile_override: str | None = None
    llm_provider_override: str | None = None
    llm_api_url_override: str | None = None
    llm_api_key_override: str | None = None
    grounded_override: bool | None = None
    content_type_override: str | None = None


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
        llm_runtime = _resolve_llm_runtime(None)
        bridge = _build_bridge_for_runtime(llm_runtime)
        await bridge.start()

        state = SessionState(
            cancel_event=asyncio.Event(),
            prompt_lock=asyncio.Lock(),
            mcp_bridge=bridge,
            repo_override=None,
            model_override=None,
            model_profile_override=None,
            llm_provider_override=None,
            llm_api_url_override=None,
            llm_api_key_override=None,
            grounded_override=None,
            content_type_override=None,
        )
        session_id = _random_session_id()
        self._sessions[session_id] = state
        await self._announce_available_commands(session_id)
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

                command_response = await _handle_grounded_command(self._conn, session_id, state, question)
                if command_response is not None:
                    return command_response

                command_response = await _handle_content_type_command(self._conn, session_id, state, question)
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

    async def _announce_available_commands(self, session_id: str) -> None:
        if not self._conn:
            return
        try:
            await self._conn.session_update(
                session_id,
                update_available_commands(AVAILABLE_SLASH_COMMANDS),
            )
        except Exception as exc:
            print(f"Erro ao anunciar comandos ACP: {exc}", file=sys.stderr)

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
    formatted_config = json.dumps(config, ensure_ascii=False, indent=2)
    reply = f"Config atual:\n```json\n{formatted_config}\n```"

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
        repo_path = Path(codebase_root) / repo
        return repo_path.exists() and repo_path.is_dir()
    except Exception:
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _resolve_llm_api_key_from_env() -> str | None:
    return (
        _coerce_optional_string(os.getenv("LLM_MODEL_API_KEY", ""))
        or _coerce_optional_string(os.getenv("LLM_API_KEY", ""))
        or _coerce_optional_string(os.getenv("OPENAI_API_KEY", ""))
    )


def _resolve_llm_runtime(state: SessionState | None) -> dict[str, str | None]:
    env_model = _coerce_optional_string(os.getenv("LLM_MODEL", ""))
    env_provider = (
        _coerce_optional_string(os.getenv("LLM_MODEL_PROVIDER", ""))
        or _coerce_optional_string(os.getenv("LLM_PROVIDER", ""))
    )
    env_api_url = (
        _coerce_optional_string(os.getenv("LLM_MODEL_API_URL", ""))
        or _coerce_optional_string(os.getenv("LLM_API_BASE_URL", ""))
    )
    env_api_key = _resolve_llm_api_key_from_env()

    model_override = state.model_override if state else None
    provider_override = state.llm_provider_override if state else None
    api_url_override = state.llm_api_url_override if state else None
    api_key_override = state.llm_api_key_override if state else None
    profile_override = state.model_profile_override if state else None

    return {
        "model": model_override or env_model,
        "provider": provider_override or env_provider,
        "api_url": api_url_override or env_api_url,
        "api_key": api_key_override or env_api_key,
        "profile": profile_override,
        "env_model": env_model,
        "env_provider": env_provider,
        "env_api_url": env_api_url,
        "env_api_key": env_api_key,
    }


def _build_bridge_for_runtime(llm_runtime: dict[str, str | None]) -> McpBridge:
    kwargs: dict[str, str | None] = {
        "llm_model": llm_runtime.get("model"),
    }

    provider = llm_runtime.get("provider")
    env_provider = llm_runtime.get("env_provider")
    api_url = llm_runtime.get("api_url")
    env_api_url = llm_runtime.get("env_api_url")
    api_key = llm_runtime.get("api_key")
    env_api_key = llm_runtime.get("env_api_key")
    if provider and provider != env_provider:
        kwargs["llm_provider"] = provider
    if api_url and api_url != env_api_url:
        kwargs["llm_api_url"] = api_url
    if api_key and api_key != env_api_key:
        kwargs["llm_api_key"] = api_key

    return build_bridge(**kwargs)


def _build_bridge_for_state(state: SessionState) -> McpBridge:
    llm_runtime = _resolve_llm_runtime(state)
    return _build_bridge_for_runtime(llm_runtime)


async def _refresh_bridge_for_model_settings(state: SessionState) -> None:
    new_bridge = _build_bridge_for_state(state)
    try:
        await new_bridge.start()
    except Exception:
        await new_bridge.close()
        raise

    previous_bridge = state.mcp_bridge
    state.mcp_bridge = new_bridge
    await previous_bridge.close()


def _snapshot_model_overrides(
    state: SessionState,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    return (
        state.model_override,
        state.model_profile_override,
        state.llm_provider_override,
        state.llm_api_url_override,
        state.llm_api_key_override,
    )


def _restore_model_overrides(
    state: SessionState,
    snapshot: tuple[str | None, str | None, str | None, str | None, str | None],
) -> None:
    (
        state.model_override,
        state.model_profile_override,
        state.llm_provider_override,
        state.llm_api_url_override,
        state.llm_api_key_override,
    ) = snapshot


def _resolve_model_profiles_path() -> Path:
    configured = _coerce_optional_string(os.getenv(MODEL_PROFILES_ENV_KEY, ""))
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_absolute():
            return configured_path
        return _repo_root() / configured_path
    return _repo_root() / DEFAULT_MODEL_PROFILES_FILE


def _load_model_profiles() -> tuple[dict[str, ModelProfile], str | None]:
    profiles_path = _resolve_model_profiles_path()
    if not profiles_path.exists():
        return {}, None

    try:
        with profiles_path.open("rb") as file_obj:
            raw = tomllib.load(file_obj)
    except Exception as exc:
        return {}, f"Falha ao ler {profiles_path}: {exc}"

    if not isinstance(raw, dict):
        return {}, f"Formato inválido em {profiles_path}: esperado objeto TOML."

    profiles_raw = raw.get("profiles")
    if not isinstance(profiles_raw, dict):
        return {}, f"{profiles_path} deve conter a seção [profiles.<nome>]."

    profiles: dict[str, ModelProfile] = {}
    for raw_name, raw_profile in profiles_raw.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            return {}, f"Perfil inválido em {profiles_path}: nome vazio."
        if not isinstance(raw_profile, dict):
            return {}, f"Perfil '{raw_name}' inválido em {profiles_path}: esperado tabela."

        profile_name = raw_name.strip()
        model = _coerce_optional_string(raw_profile.get("model"))
        if not model:
            return {}, f"Perfil '{profile_name}' sem campo obrigatório 'model'."

        provider = _coerce_optional_string(raw_profile.get("provider"))
        api_url = _coerce_optional_string(raw_profile.get("api_url"))
        api_key = _coerce_optional_string(raw_profile.get("api_key"))
        api_key_env = _coerce_optional_string(raw_profile.get("api_key_env"))
        if api_key_env:
            api_key = _coerce_optional_string(os.getenv(api_key_env, "")) or api_key

        profile = ModelProfile(
            name=profile_name,
            model=model,
            provider=provider,
            api_url=api_url,
            api_key=api_key,
        )
        profiles[profile_name.lower()] = profile

    return profiles, None


def _resolve_model_profile_by_selector(selector: str) -> tuple[ModelProfile | None, str | None]:
    normalized = selector.strip().lower()
    if normalized.startswith("profile:"):
        normalized = normalized.partition(":")[2].strip()
    if not normalized:
        return None, None

    profiles, error = _load_model_profiles()
    if error:
        return None, error
    if not profiles:
        return None, None

    exact = profiles.get(normalized)
    if exact is not None:
        return exact, None

    model_matches = [profile for profile in profiles.values() if profile.model.lower() == normalized]
    if len(model_matches) == 1:
        return model_matches[0], None
    if len(model_matches) > 1:
        names = ", ".join(sorted(profile.name for profile in model_matches))
        return None, f"Modelo '{selector}' é ambíguo. Perfis possíveis: {names}."
    return None, None


def _build_runtime_config(state: SessionState) -> dict[str, Any]:
    payload_preview = _build_ask_payload("<query>", state)
    payload_preview.pop("query", None)

    active_repo = (state.repo_override or os.getenv("ACP_REPO", "code-compass")).strip()
    llm_runtime = _resolve_llm_runtime(state)
    content_type_env = _resolve_content_type_from_env()
    content_type_active = _resolve_content_type(state)
    grounded_env = _is_truthy(os.getenv("ACP_GROUNDED", ""))
    grounded_active = _resolve_grounded(state)

    return {
        "scope": payload_preview.get("scope"),
        "repo": {
            "active": active_repo,
            "override": state.repo_override,
            "env": os.getenv("ACP_REPO", "code-compass").strip(),
        },
        "model": {
            "active": llm_runtime.get("model"),
            "override": state.model_override,
            "env": llm_runtime.get("env_model"),
            "profile": llm_runtime.get("profile"),
            "provider": {
                "active": llm_runtime.get("provider"),
                "override": state.llm_provider_override,
                "env": llm_runtime.get("env_provider"),
            },
            "apiUrl": {
                "active": llm_runtime.get("api_url"),
                "override": state.llm_api_url_override,
                "env": llm_runtime.get("env_api_url"),
            },
            "apiKey": {
                "activeConfigured": bool(llm_runtime.get("api_key")),
                "overrideConfigured": bool(state.llm_api_key_override),
                "envConfigured": bool(llm_runtime.get("env_api_key")),
            },
        },
        "grounded": {
            "active": grounded_active,
            "override": state.grounded_override,
            "env": grounded_env,
        },
        "contentType": {
            "active": content_type_active,
            "override": state.content_type_override,
            "env": content_type_env,
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
    llm_model = _resolve_llm_runtime(state).get("model")
    grounded = _resolve_grounded(state)
    content_type = _resolve_content_type(state)
    strict = _is_truthy(os.getenv("ACP_STRICT", ""))

    if path_prefix:
        payload["pathPrefix"] = path_prefix
    if language:
        payload["language"] = language
    if top_k is not None:
        payload["topK"] = top_k
    if min_score is not None:
        payload["minScore"] = min_score
    if isinstance(llm_model, str) and llm_model:
        payload["llmModel"] = llm_model
    if grounded:
        payload["grounded"] = True
    if content_type:
        payload["contentType"] = content_type
    if strict:
        payload["strict"] = True

    return payload


def _resolve_grounded(state: SessionState) -> bool:
    if state.grounded_override is not None:
        return state.grounded_override
    return _is_truthy(os.getenv("ACP_GROUNDED", ""))


def _resolve_content_type_from_env() -> str | None:
    content_type = os.getenv("ACP_CONTENT_TYPE", "").strip().lower()
    if content_type in VALID_CONTENT_TYPES:
        return content_type
    return None


def _resolve_content_type(state: SessionState) -> str | None:
    if state.content_type_override in VALID_CONTENT_TYPES:
        return state.content_type_override
    return _resolve_content_type_from_env()


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
        llm_runtime = _resolve_llm_runtime(state)
        active_model = llm_runtime.get("model") or "default"
        active_profile = llm_runtime.get("profile")
        if active_profile:
            reply = f"Modelo atual: {active_model} (perfil: {active_profile})"
        else:
            reply = f"Modelo atual: {active_model}"
    else:
        selector = parts[1].strip()
        if not selector:
            reply = "Nome do modelo vazio. Use /model <nome>."
        else:
            previous_snapshot = _snapshot_model_overrides(state)
            state_changed = False
            try:
                if selector.lower() in MODEL_RESET_VALUES:
                    state.model_override = None
                    state.model_profile_override = None
                    state.llm_provider_override = None
                    state.llm_api_url_override = None
                    state.llm_api_key_override = None
                    state_changed = True
                    await _refresh_bridge_for_model_settings(state)
                    reply = "Modelo resetado para o default."
                else:
                    profile, profile_error = _resolve_model_profile_by_selector(selector)
                    if profile_error:
                        if selector.lower().startswith("profile:"):
                            reply = (
                                "Falha ao carregar perfis de modelo. "
                                f"Detalhe técnico: {profile_error}"
                            )
                        else:
                            state.model_override = selector
                            state.model_profile_override = None
                            state.llm_provider_override = None
                            state.llm_api_url_override = None
                            state.llm_api_key_override = None
                            state_changed = True
                            await _refresh_bridge_for_model_settings(state)
                            reply = (
                                f"Modelo atualizado para: {state.model_override}. "
                                "Perfis indisponíveis no momento."
                            )
                    elif profile is not None:
                        state.model_override = profile.model
                        state.model_profile_override = profile.name
                        state.llm_provider_override = profile.provider
                        state.llm_api_url_override = profile.api_url
                        state.llm_api_key_override = profile.api_key
                        state_changed = True
                        await _refresh_bridge_for_model_settings(state)

                        provider = profile.provider or "env"
                        api_url = profile.api_url or "env"
                        key_status = "configurada" if profile.api_key else "env/default"
                        reply = (
                            f"Perfil '{profile.name}' ativado: "
                            f"model={profile.model}, provider={provider}, api_url={api_url}, api_key={key_status}."
                        )
                    else:
                        state.model_override = selector
                        state.model_profile_override = None
                        state.llm_provider_override = None
                        state.llm_api_url_override = None
                        state.llm_api_key_override = None
                        state_changed = True
                        await _refresh_bridge_for_model_settings(state)
                        reply = f"Modelo atualizado para: {state.model_override}"
            except Exception as exc:
                if state_changed:
                    _restore_model_overrides(state, previous_snapshot)
                reply = (
                    "Falha ao aplicar configuração de modelo. "
                    f"Detalhe técnico: {exc}"
                )

    if conn:
        await conn.session_update(session_id, acp.update_agent_message_text(reply))
    return acp.PromptResponse(stop_reason="end_turn")


async def _handle_grounded_command(
    conn: acp.Client | None,
    session_id: str,
    state: SessionState,
    question: str,
) -> acp.PromptResponse | None:
    text = question.strip()
    if not text.startswith("/grounded"):
        return None

    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        status = "on" if _resolve_grounded(state) else "off"
        source = "sessão" if state.grounded_override is not None else "env"
        reply = f"Grounded atual: {status} (fonte: {source})."
    else:
        value = parts[1].strip().lower()
        if value in GROUNDED_ON_VALUES:
            state.grounded_override = True
            reply = "Grounded ativado para esta sessão."
        elif value in GROUNDED_OFF_VALUES:
            state.grounded_override = False
            reply = "Grounded desativado para esta sessão."
        elif value in {"reset", "default"}:
            state.grounded_override = None
            reply = "Grounded resetado para o valor do ambiente."
        else:
            reply = "Valor inválido. Use /grounded on|off|reset."

    if conn:
        await conn.session_update(session_id, acp.update_agent_message_text(reply))
    return acp.PromptResponse(stop_reason="end_turn")


async def _handle_content_type_command(
    conn: acp.Client | None,
    session_id: str,
    state: SessionState,
    question: str,
) -> acp.PromptResponse | None:
    text = question.strip()
    if not text.startswith("/"):
        return None

    command, _, raw_args = text.partition(" ")
    normalized = command.lower().replace("-", "")
    if normalized != "/contenttype":
        return None

    value = raw_args.strip().lower()
    if not value:
        active = _resolve_content_type(state)
        source = "sessão" if state.content_type_override is not None else "env"
        if active is None:
            source = "default"
        reply = f"contentType atual: {active or 'default'} (fonte: {source})."
    elif value in VALID_CONTENT_TYPES:
        state.content_type_override = value
        reply = f"contentType atualizado para: {value}"
    elif value in {"reset", "default"}:
        state.content_type_override = None
        reply = "contentType resetado para o valor do ambiente."
    else:
        reply = "Valor inválido. Use /content-type code|docs|all|reset."

    if conn:
        await conn.session_update(session_id, acp.update_agent_message_text(reply))
    return acp.PromptResponse(stop_reason="end_turn")


def _random_session_id() -> str:
    return f"session-{os.urandom(6).hex()}"
