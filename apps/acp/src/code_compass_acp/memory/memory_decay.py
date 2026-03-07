from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from .env_utils import env_float


@dataclass(frozen=True)
class MemoryDecayConfig:
    preference_lambda: float = 0.08
    convention_lambda: float = 0.03
    fact_lambda: float = 0.01
    reinforcement_step: float = 0.08
    reinforcement_cap: float = 1.6

    @classmethod
    def from_env(cls) -> MemoryDecayConfig:
        return cls(
            preference_lambda=env_float("ACP_MEMORY_DECAY_PREFERENCE_LAMBDA", 0.08),
            convention_lambda=env_float("ACP_MEMORY_DECAY_CONVENTION_LAMBDA", 0.03),
            fact_lambda=env_float("ACP_MEMORY_DECAY_FACT_LAMBDA", 0.01),
            reinforcement_step=env_float("ACP_MEMORY_REINFORCEMENT_STEP", 0.08),
            reinforcement_cap=env_float("ACP_MEMORY_REINFORCEMENT_CAP", 1.6),
        )


def _lambda_for_kind(kind: str, config: MemoryDecayConfig) -> float:
    normalized = kind.strip().lower()
    if normalized in {"preference", "opinion"}:
        return config.preference_lambda
    if normalized in {"convention", "decision"}:
        return config.convention_lambda
    if normalized in {"fact", "profile"}:
        return config.fact_lambda
    return config.convention_lambda


def calculate_effective_confidence(
    *,
    confidence: float,
    kind: str,
    created_at: datetime,
    last_confirmed_at: datetime | None,
    times_reinforced: int,
    now: datetime | None = None,
    config: MemoryDecayConfig | None = None,
) -> float:
    runtime_config = config or MemoryDecayConfig.from_env()
    current = now or datetime.now(tz=UTC)
    reference = last_confirmed_at or created_at
    age_seconds = max((current - reference).total_seconds(), 0.0)
    age_days = age_seconds / 86_400.0
    decay = math.exp(-_lambda_for_kind(kind, runtime_config) * age_days)
    reinforcement_factor = min(
        1.0 + max(times_reinforced, 0) * runtime_config.reinforcement_step,
        runtime_config.reinforcement_cap,
    )
    effective = confidence * decay * reinforcement_factor
    return max(0.0, min(effective, 1.0))
