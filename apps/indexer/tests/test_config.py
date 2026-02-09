from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from indexer.config import DEFAULT_IGNORE_DIRS, load_scan_config


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


if __name__ == "__main__":
    unittest.main()

