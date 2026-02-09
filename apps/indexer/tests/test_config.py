from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from indexer.config import (
    DEFAULT_CHUNK_LINES,
    DEFAULT_CHUNK_OVERLAP_LINES,
    DEFAULT_IGNORE_DIRS,
    load_chunk_config,
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


if __name__ == "__main__":
    unittest.main()
