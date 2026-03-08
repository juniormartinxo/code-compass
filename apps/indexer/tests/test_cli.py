from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
            self.assertEqual(first_chunk["chunkSchemaVersion"], "v2")
            self.assertEqual(first_chunk["chunkStrategy"], "line_window")
            self.assertIn("summaryText", first_chunk)
            self.assertIn("contextText", first_chunk)
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

    def test_cli_ask_requires_scope(self) -> None:
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
        self.assertIn("informe um escopo", completed.stderr)


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


class IndexPreflightTests(unittest.TestCase):
    def test_preflight_rejects_legacy_chunk_schema_points(self) -> None:
        from indexer.__main__ import _fail_if_legacy_chunk_schema_points
        from indexer.qdrant_store import QdrantStoreError

        store = mock.Mock()
        store.count_points_without_payload_match.side_effect = [2, 0]

        with self.assertRaisesRegex(
            QdrantStoreError,
            "reindexacao completa obrigatoria",
        ):
            _fail_if_legacy_chunk_schema_points(
                store=store,
                collection_names={"code": "shared__code", "docs": "shared__docs"},
                content_types=("code", "docs"),
            )

        self.assertEqual(store.count_points_without_payload_match.call_count, 2)

    def test_preflight_allows_collections_when_only_v2_points_exist(self) -> None:
        from indexer.__main__ import _fail_if_legacy_chunk_schema_points

        store = mock.Mock()
        store.count_points_without_payload_match.side_effect = [0, 0]

        _fail_if_legacy_chunk_schema_points(
            store=store,
            collection_names={"code": "shared__code", "docs": "shared__docs"},
            content_types=("code", "docs"),
        )

        self.assertEqual(store.count_points_without_payload_match.call_count, 2)

    def test_preflight_rejects_same_repo_name_from_other_repo_root(self) -> None:
        from indexer.__main__ import _fail_if_repo_name_collides_with_other_repo_root
        from indexer.qdrant_store import QdrantStoreError

        store = mock.Mock()
        store.count_points.side_effect = [1, 0]

        with self.assertRaisesRegex(
            QdrantStoreError,
            "basename duplicado",
        ):
            _fail_if_repo_name_collides_with_other_repo_root(
                store=store,
                collection_names={"code": "shared__code", "docs": "shared__docs"},
                content_types=("code", "docs"),
                repo="shared-lib",
                repo_root=Path("/tmp/code-base-a/shared-lib"),
            )

        self.assertEqual(store.count_points.call_count, 2)
        _, kwargs = store.count_points.call_args_list[0]
        count_filter = kwargs["count_filter"]
        self.assertEqual(count_filter.must[0].key, "repo")
        self.assertEqual(count_filter.must[0].match.value, "shared-lib")
        self.assertEqual(count_filter.must_not[0].key, "repo_root")
        self.assertEqual(
            count_filter.must_not[0].match.value,
            "/tmp/code-base-a/shared-lib",
        )

    def test_preflight_allows_same_repo_name_when_repo_root_matches(self) -> None:
        from indexer.__main__ import _fail_if_repo_name_collides_with_other_repo_root

        store = mock.Mock()
        store.count_points.side_effect = [0, 0]

        _fail_if_repo_name_collides_with_other_repo_root(
            store=store,
            collection_names={"code": "shared__code", "docs": "shared__docs"},
            content_types=("code", "docs"),
            repo="shared-lib",
            repo_root=Path("/tmp/code-base-a/shared-lib"),
        )

        self.assertEqual(store.count_points.call_count, 2)


if __name__ == "__main__":
    unittest.main()
