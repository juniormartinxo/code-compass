from __future__ import annotations

from pydantic import BaseModel


class CliConfig(BaseModel):
    repo: str | None = None
    path_prefix: str | None = None
    language: str | None = None
    top_k: int = 10
    min_score: float = 0.6
    timeout_ms: int = 120_000
    llm_model: str | None = None
    debug: bool = False

    mcp_command: str | None = None
    toad_profile: str | None = None
