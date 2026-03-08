from __future__ import annotations

from pathlib import Path

from .config import RuntimeConfig, load_runtime_config


def find_doc_path_hint(
    path: str,
    runtime_config: RuntimeConfig | None = None,
) -> str | None:
    config = runtime_config or load_runtime_config()
    normalized = f"/{path.replace('\\', '/').strip('/').lower()}"
    for hint in config.doc_path_hints:
        if hint in normalized:
            return hint
    return None


def classify_content_type(
    path: str,
    runtime_config: RuntimeConfig | None = None,
) -> tuple[str, str | None]:
    config = runtime_config or load_runtime_config()
    ext = Path(path).suffix.lower()
    path_hint = find_doc_path_hint(path, runtime_config=config)
    if path_hint is not None or ext in config.doc_extensions:
        return "docs", path_hint
    return "code", path_hint
