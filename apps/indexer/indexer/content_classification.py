from __future__ import annotations

from pathlib import Path

from .config import RuntimeConfig, load_runtime_config

DOC_SECTION_CONTENT_TYPE = "doc_section"
CODE_CONTEXT_CONTENT_TYPE = "code_context"
CODE_SYMBOL_CONTENT_TYPE = "code_symbol"
CONFIG_BLOCK_CONTENT_TYPE = "config_block"
SQL_BLOCK_CONTENT_TYPE = "sql_block"
TEST_CASE_CONTENT_TYPE = "test_case"

_DOCS_COLLECTION_CONTENT_TYPE = "docs"
_CODE_COLLECTION_CONTENT_TYPE = "code"
_TEST_PATH_MARKERS: tuple[str, ...] = (
    "/tests/",
    "/test/",
    "/__tests__/",
    "/spec/",
    "/specs/",
)
_TEST_FILE_MARKERS: tuple[str, ...] = (
    ".test.",
    ".spec.",
    "_test.",
    "_spec.",
)
_CONFIG_SUFFIXES: set[str] = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
}
_CONFIG_PATH_MARKERS: tuple[str, ...] = (
    "/config/",
    "/configs/",
    "/conf/",
    "/settings/",
)
_CONFIG_FILE_NAMES: set[str] = {
    ".env",
    "package.json",
    "pyproject.toml",
    "tsconfig.json",
    "jsconfig.json",
    "nest-cli.json",
    "docker-compose.yml",
    "docker-compose.yaml",
}
_CONFIG_STEM_MARKERS: tuple[str, ...] = (
    "config",
    "settings",
    "profile",
    "compose",
)
_SQL_SUFFIXES: set[str] = {".sql"}
_COLLECTION_CONTENT_TYPE_BY_CHUNK_CONTENT_TYPE: dict[str, str] = {
    DOC_SECTION_CONTENT_TYPE: _DOCS_COLLECTION_CONTENT_TYPE,
    CODE_CONTEXT_CONTENT_TYPE: _CODE_COLLECTION_CONTENT_TYPE,
    CODE_SYMBOL_CONTENT_TYPE: _CODE_COLLECTION_CONTENT_TYPE,
    CONFIG_BLOCK_CONTENT_TYPE: _CODE_COLLECTION_CONTENT_TYPE,
    SQL_BLOCK_CONTENT_TYPE: _CODE_COLLECTION_CONTENT_TYPE,
    TEST_CASE_CONTENT_TYPE: _CODE_COLLECTION_CONTENT_TYPE,
}


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


def resolve_collection_content_type(content_type: str) -> str:
    try:
        return _COLLECTION_CONTENT_TYPE_BY_CHUNK_CONTENT_TYPE[content_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported chunk content type: {content_type}") from exc


def _normalize_path(path: str) -> str:
    return f"/{path.replace('\\', '/').strip('/').lower()}"


def _is_test_case_path(normalized_path: str, file_name: str) -> bool:
    if any(marker in normalized_path for marker in _TEST_PATH_MARKERS):
        return True
    if file_name.startswith("test_"):
        return True
    return any(marker in file_name for marker in _TEST_FILE_MARKERS)


def _is_config_path(normalized_path: str, ext: str, file_name: str) -> bool:
    if normalized_path.endswith("/.env") or file_name == ".env":
        return True
    if ext not in _CONFIG_SUFFIXES:
        return False
    if file_name in _CONFIG_FILE_NAMES:
        return True

    stem = Path(file_name).stem.lower()
    if any(marker in stem for marker in _CONFIG_STEM_MARKERS):
        return True

    return any(marker in normalized_path for marker in _CONFIG_PATH_MARKERS)


def classify_content_type(
    path: str,
    runtime_config: RuntimeConfig | None = None,
) -> tuple[str, str | None]:
    config = runtime_config or load_runtime_config()
    path_obj = Path(path)
    ext = path_obj.suffix.lower()
    file_name = path_obj.name.lower()
    normalized_path = _normalize_path(path)
    path_hint = find_doc_path_hint(path, runtime_config=config)

    if path_hint is not None or ext in config.doc_extensions:
        return DOC_SECTION_CONTENT_TYPE, path_hint
    if _is_test_case_path(normalized_path, file_name):
        return TEST_CASE_CONTENT_TYPE, path_hint
    if ext in _SQL_SUFFIXES:
        return SQL_BLOCK_CONTENT_TYPE, path_hint
    if _is_config_path(normalized_path, ext, file_name):
        return CONFIG_BLOCK_CONTENT_TYPE, path_hint
    return CODE_CONTEXT_CONTENT_TYPE, path_hint
