from __future__ import annotations

import argparse
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


class ChunkCliTests(unittest.TestCase):
    def test_cli_chunk_outputs_expected_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "main.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "\n".join([f"line {index}" for index in range(1, 8)]) + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "indexer",
                    "chunk",
                    "--file",
                    str(file_path),
                    "--repo-root",
                    str(repo_root),
                    "--chunk-lines",
                    "4",
                    "--overlap-lines",
                    "1",
                    "--as-posix",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["path"], "src/main.py")
            self.assertTrue(payload["pathIsRelative"])
            self.assertTrue(payload["asPosix"])
            self.assertEqual(payload["chunkLines"], 4)
            self.assertEqual(payload["overlapLines"], 1)
            self.assertEqual(payload["totalLines"], 7)
            self.assertEqual(payload["stats"]["chunks"], 2)

            first_chunk = payload["chunks"][0]
            second_chunk = payload["chunks"][1]
            self.assertEqual(first_chunk["startLine"], 1)
            self.assertEqual(first_chunk["endLine"], 4)
            self.assertEqual(second_chunk["startLine"], 4)
            self.assertEqual(second_chunk["endLine"], 7)
            self.assertEqual(first_chunk["language"], "python")
            self.assertEqual(payload["warnings"], [])

    def test_cli_chunk_rejects_invalid_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "sample.md"
            file_path.write_text("one\ntwo\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "indexer",
                    "chunk",
                    "--file",
                    str(file_path),
                    "--repo-root",
                    str(repo_root),
                    "--chunk-lines",
                    "4",
                    "--overlap-lines",
                    "4",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertIn("overlap deve ser menor que chunk_lines", completed.stderr)


class AskCliTests(unittest.TestCase):
    def test_cli_ask_rejects_empty_question(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "indexer",
                "ask",
                "",
                "--model",
                "gpt-oss",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("Erro: pergunta vazia.", completed.stderr)

    def test_cli_ask_requires_repo_or_scope(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "indexer",
                "ask",
                "qual repo?",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("informe --repo", completed.stderr)


class AskScopePayloadTests(unittest.TestCase):
    def _ask_args(self, **kwargs: object) -> argparse.Namespace:
        from indexer.__main__ import _build_parser

        parser = _build_parser()
        base = ["ask", "pergunta"]
        for key, value in kwargs.items():
            if isinstance(value, bool):
                if value:
                    base.append(f"--{key.replace('_', '-')}")
            else:
                base.extend([f"--{key.replace('_', '-')}", str(value)])
        return parser.parse_args(base)

    def test_scope_payload_uses_repo_compat(self) -> None:
        from indexer.__main__ import _build_ask_scope_payload

        args = self._ask_args(repo="acme-portal")
        payload = _build_ask_scope_payload(args)
        self.assertEqual(payload, {"repo": "acme-portal"})

    def test_scope_payload_uses_scope_repo(self) -> None:
        from indexer.__main__ import _build_ask_scope_payload

        args = self._ask_args(scope_repo="shared-lib")
        payload = _build_ask_scope_payload(args)
        self.assertEqual(payload, {"scope": {"type": "repo", "repo": "shared-lib"}})

    def test_scope_payload_uses_scope_repos(self) -> None:
        from indexer.__main__ import _build_ask_scope_payload

        args = self._ask_args(scope_repos="repo-a, repo-b")
        payload = _build_ask_scope_payload(args)
        self.assertEqual(
            payload,
            {"scope": {"type": "repos", "repos": ["repo-a", "repo-b"]}},
        )

    def test_scope_payload_uses_scope_all(self) -> None:
        from indexer.__main__ import _build_ask_scope_payload

        args = self._ask_args(scope_all=True)
        payload = _build_ask_scope_payload(args)
        self.assertEqual(payload, {"scope": {"type": "all"}})


if __name__ == "__main__":
    unittest.main()
