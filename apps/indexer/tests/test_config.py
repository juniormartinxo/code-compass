from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from indexer.config import (
    DEFAULT_CHUNK_LINES,
    DEFAULT_CHUNK_OVERLAP_LINES,
    DEFAULT_CONTENT_TYPES,
    DEFAULT_DOC_EXTENSIONS,
    DEFAULT_DOC_PATH_HINTS,
    DEFAULT_EXCLUDED_CONTEXT_PATH_PARTS,
    DEFAULT_IGNORE_DIRS,
    DEFAULT_MIN_FILE_COVERAGE,
    DEFAULT_SEARCH_SNIPPET_MAX_CHARS,
    load_chunk_config,
    load_runtime_config,
    load_scan_config,
)


class ScanConfigTests(unittest.TestCase):
    def test_load_scan_config_uses_default_repo_root_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = root / "runner"
            runner.mkdir()

            previous_cwd = Path.cwd()
            try:
                os.chdir(runner)
                with patch.dict(os.environ, {}, clear=True):
                    config = load_scan_config()
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(config.repo_root, root.resolve())
            self.assertEqual(config.ignore_dirs, DEFAULT_IGNORE_DIRS)

    def test_load_scan_config_supports_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()

            with patch.dict(
                os.environ,
                {
                    "REPO_ROOT": str(repo_root),
                    "SCAN_IGNORE_DIRS": "tmp,node_modules",
                    "SCAN_ALLOW_EXTS": "py,.MD",
                },
                clear=True,
            ):
                config = load_scan_config()

            self.assertEqual(config.repo_root, repo_root.resolve())
            self.assertIn("tmp", config.ignore_dirs)
            self.assertIn("node_modules", config.ignore_dirs)
            self.assertEqual(config.allow_exts, {".py", ".md"})

    def test_load_scan_config_defaults_include_python_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()

            with patch.dict(
                os.environ,
                {"REPO_ROOT": str(repo_root)},
                clear=True,
            ):
                config = load_scan_config()

            self.assertIn(".venv", config.ignore_dirs)
            self.assertIn("venv", config.ignore_dirs)
            self.assertIn("__pycache__", config.ignore_dirs)
            self.assertIn(".pytest_cache", config.ignore_dirs)


class ChunkConfigTests(unittest.TestCase):
    def test_load_chunk_config_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = root / "runner"
            runner.mkdir()

            previous_cwd = Path.cwd()
            try:
                os.chdir(runner)
                with patch.dict(os.environ, {}, clear=True):
                    config = load_chunk_config()
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(config.repo_root, root.resolve())
            self.assertEqual(config.chunk_lines, DEFAULT_CHUNK_LINES)
            self.assertEqual(config.overlap_lines, DEFAULT_CHUNK_OVERLAP_LINES)

    def test_load_chunk_config_supports_env_and_args(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            repo_root.mkdir()

            with patch.dict(
                os.environ,
                {
                    "REPO_ROOT": str(repo_root),
                    "CHUNK_LINES": "64",
                    "CHUNK_OVERLAP_LINES": "8",
                },
                clear=True,
            ):
                config_env = load_chunk_config()
                config_args = load_chunk_config(chunk_lines=32, overlap_lines=4)

            self.assertEqual(config_env.repo_root, repo_root.resolve())
            self.assertEqual(config_env.chunk_lines, 64)
            self.assertEqual(config_env.overlap_lines, 8)
            self.assertEqual(config_args.chunk_lines, 32)
            self.assertEqual(config_args.overlap_lines, 4)

    def test_load_chunk_config_rejects_invalid_integers(self) -> None:
        with patch.dict(os.environ, {"CHUNK_LINES": "abc"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CHUNK_LINES"):
                load_chunk_config()


class RuntimeConfigTests(unittest.TestCase):
    def test_load_runtime_config_uses_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_runtime_config()

        self.assertEqual(
            config.excluded_context_path_parts,
            DEFAULT_EXCLUDED_CONTEXT_PATH_PARTS,
        )
        self.assertEqual(
            config.search_snippet_max_chars,
            DEFAULT_SEARCH_SNIPPET_MAX_CHARS,
        )
        self.assertEqual(config.doc_extensions, DEFAULT_DOC_EXTENSIONS)
        self.assertEqual(config.doc_path_hints, DEFAULT_DOC_PATH_HINTS)
        self.assertEqual(config.content_types, DEFAULT_CONTENT_TYPES)
        self.assertEqual(config.min_file_coverage, DEFAULT_MIN_FILE_COVERAGE)

    def test_load_runtime_config_supports_env_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EXCLUDED_CONTEXT_PATH_PARTS": ".venv,tmp/cache",
                "SEARCH_SNIPPET_MAX_CHARS": "180",
                "DOC_EXTENSIONS": "md,markdown",
                "DOC_PATH_HINTS": "docs,handbook/",
                "CONTENT_TYPES": "docs,code",
                "INDEX_MIN_FILE_COVERAGE": "0.8",
            },
            clear=True,
        ):
            config = load_runtime_config()

        self.assertEqual(config.excluded_context_path_parts, ("/.venv/", "/tmp/cache/"))
        self.assertEqual(config.search_snippet_max_chars, 180)
        self.assertEqual(config.doc_extensions, {".md", ".markdown"})
        self.assertEqual(config.doc_path_hints, ("/docs", "/handbook/"))
        self.assertEqual(config.content_types, ("docs", "code"))
        self.assertEqual(config.min_file_coverage, 0.8)

    def test_load_runtime_config_falls_back_when_env_is_invalid(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SEARCH_SNIPPET_MAX_CHARS": "-1",
                "DOC_EXTENSIONS": "",
                "DOC_PATH_HINTS": "",
                "CONTENT_TYPES": "docs",
                "INDEX_MIN_FILE_COVERAGE": "abc",
            },
            clear=True,
        ):
            config = load_runtime_config()

        self.assertEqual(
            config.search_snippet_max_chars,
            DEFAULT_SEARCH_SNIPPET_MAX_CHARS,
        )
        self.assertEqual(config.doc_extensions, DEFAULT_DOC_EXTENSIONS)
        self.assertEqual(config.doc_path_hints, DEFAULT_DOC_PATH_HINTS)
        self.assertEqual(config.content_types, DEFAULT_CONTENT_TYPES)
        self.assertEqual(config.min_file_coverage, DEFAULT_MIN_FILE_COVERAGE)


if __name__ == "__main__":
    unittest.main()
