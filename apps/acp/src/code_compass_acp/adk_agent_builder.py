from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import Callable

from .adk_runtime import (
    AdkRuntimeAdapter,
    LegacyRuntimeAdapter,
    RuntimeAdapter,
    resolve_engine,
    resolve_runtime_mode,
)
from .bridge import McpBridge
from .bridge import build_bridge


@dataclass(frozen=True)
class RuntimeBuildResult:
    adapter: RuntimeAdapter
    runtime_mode: str
    memory_backend: str
    session_backend: str
    memory_index_backend: str


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_session_backend(runtime_mode: str) -> str:
    raw = os.getenv("ACP_SESSION_BACKEND", "").strip().lower()
    if raw in {"memory", "sqlite"}:
        return raw
    if runtime_mode == "local":
        return "sqlite"
    return "memory"


def _resolve_memory_index_backend(runtime_mode: str) -> str:
    if runtime_mode == "cloud":
        return "vertex_vector_search"
    if _is_truthy(os.getenv("ACP_MEMORY_QDRANT_INDEX_ENABLED", "")):
        return "qdrant"
    return "none"


def _build_bridge_compat(
    llm_runtime: dict[str, str | None],
    *,
    build_bridge_fn: Callable[..., McpBridge],
) -> McpBridge:
    kwargs: dict[str, str | None] = {"llm_model": llm_runtime.get("model")}
    provider = llm_runtime.get("provider")
    api_url = llm_runtime.get("api_url")
    api_key = llm_runtime.get("api_key")
    if provider:
        kwargs["llm_provider"] = provider
    if api_url:
        kwargs["llm_api_url"] = api_url
    if api_key:
        kwargs["llm_api_key"] = api_key

    # TODO: remover reflexão de assinatura quando todos os callers/testes
    # estiverem padronizados com `build_bridge(**kwargs)`.
    signature = inspect.signature(build_bridge_fn)
    parameters = list(signature.parameters.values())
    accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters)

    if accepts_var_kwargs:
        return build_bridge_fn(**kwargs)

    accepted_keyword_names = {
        param.name
        for param in parameters
        if param.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    filtered_kwargs = {key: value for key, value in kwargs.items() if key in accepted_keyword_names}
    if filtered_kwargs:
        return build_bridge_fn(**filtered_kwargs)

    positional_params = [
        param
        for param in parameters
        if param.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if positional_params:
        return build_bridge_fn(kwargs.get("llm_model"))

    return build_bridge_fn()


def build_runtime_adapter(
    llm_runtime: dict[str, str | None],
    *,
    build_bridge_fn: Callable[..., McpBridge] = build_bridge,
) -> RuntimeBuildResult:
    runtime_mode = resolve_runtime_mode()
    engine = resolve_engine()
    if engine == "adk":
        adapter: RuntimeAdapter = AdkRuntimeAdapter(runtime_mode=runtime_mode)
    else:
        adapter = LegacyRuntimeAdapter(
            _build_bridge_compat(llm_runtime, build_bridge_fn=build_bridge_fn)
        )

    session_backend = _resolve_session_backend(runtime_mode)
    memory_backend = "sqlite" if runtime_mode == "local" else "vertex_memory_bank"
    memory_index_backend = _resolve_memory_index_backend(runtime_mode)
    return RuntimeBuildResult(
        adapter=adapter,
        runtime_mode=runtime_mode,
        memory_backend=memory_backend,
        session_backend=session_backend,
        memory_index_backend=memory_index_backend,
    )
