from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ScanCliTests(unittest.TestCase):
    def test_cli_scan_outputs_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src").mkdir()
            (repo_root / "src" / "main.ts").write_text("const ok = true;\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "indexer",
                    "scan",
                    "--repo-root",
                    str(repo_root),
                    "--allow-exts",
                    ".ts",
                    "--ignore-dirs",
                    "node_modules",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)
            self.assertIn("repoRoot", payload)
            self.assertIn("ignoreDirs", payload)
            self.assertIn("allowExts", payload)
            self.assertIn("stats", payload)
            self.assertEqual(payload["files"], ["src/main.ts"])

    def test_cli_returns_error_for_invalid_repo_root(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "indexer",
                "scan",
                "--repo-root",
                "/tmp/indexer-scan-invalid-root-does-not-exist",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("REPO_ROOT inválido ou inexistente", completed.stderr)


if __name__ == "__main__":
    unittest.main()

