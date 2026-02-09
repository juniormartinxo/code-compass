from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from indexer.chunk import (
    chunk_file,
    chunk_lines,
    detect_language,
    hash_content,
    make_chunk_id,
    normalize_path,
    read_text,
)


class ChunkCoreTests(unittest.TestCase):
    def test_chunk_lines_generates_expected_overlap_and_ranges(self) -> None:
        lines = [f"line {index}" for index in range(1, 8)]

        chunks = chunk_lines(lines=lines, chunk_lines=4, overlap=1)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0][0], 1)
        self.assertEqual(chunks[0][1], 4)
        self.assertEqual(chunks[1][0], 4)
        self.assertEqual(chunks[1][1], 7)

        start_a, end_a, _ = chunks[0]
        start_b, _, _ = chunks[1]
        self.assertEqual(start_b, start_a + (4 - 1))
        self.assertEqual(end_a - start_b + 1, 1)

    def test_chunk_lines_rejects_invalid_overlap(self) -> None:
        with self.assertRaisesRegex(ValueError, "menor que chunk_lines"):
            chunk_lines(lines=["a"], chunk_lines=3, overlap=3)

        with self.assertRaisesRegex(ValueError, "maior que 0"):
            chunk_lines(lines=["a"], chunk_lines=0, overlap=0)

        with self.assertRaisesRegex(ValueError, "maior ou igual"):
            chunk_lines(lines=["a"], chunk_lines=2, overlap=-1)

    def test_hash_and_chunk_id_are_deterministic(self) -> None:
        content = "alpha\nbeta\n"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        content_hash = hash_content(content)

        self.assertEqual(content_hash, expected_hash)

        chunk_id = make_chunk_id("apps/indexer/file.py", 1, 2, content_hash)
        same_chunk_id = make_chunk_id("apps/indexer/file.py", 1, 2, content_hash)
        different_path = make_chunk_id("apps/indexer/other.py", 1, 2, content_hash)
        different_range = make_chunk_id("apps/indexer/file.py", 2, 2, content_hash)

        self.assertEqual(chunk_id, same_chunk_id)
        self.assertNotEqual(chunk_id, different_path)
        self.assertNotEqual(chunk_id, different_range)

    def test_normalize_path_relative_and_absolute_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_inside = root / "apps" / "indexer" / "sample.py"
            file_inside.parent.mkdir(parents=True)
            file_inside.write_text("print('ok')\n", encoding="utf-8")

            relative = normalize_path(file_inside, root, as_posix=True)
            self.assertEqual(relative, "apps/indexer/sample.py")

            outside_root = root / "other"
            outside_root.mkdir()
            fallback = normalize_path(outside_root, root / "apps", as_posix=True)
            self.assertEqual(fallback, outside_root.resolve().as_posix())

    def test_detect_language_uses_extension_map(self) -> None:
        self.assertEqual(detect_language(Path("a.tsx")), "typescriptreact")
        self.assertEqual(detect_language(Path("a.yml")), "yaml")
        self.assertEqual(detect_language(Path("a.unknown")), "text")

    def test_read_text_supports_utf8_sig_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bom.txt"
            path.write_text("hello", encoding="utf-8-sig")

            text, encoding = read_text(path)

            self.assertEqual(encoding, "utf-8-sig")
            self.assertEqual(text, "hello")


class ChunkFileTests(unittest.TestCase):
    def test_chunk_file_builds_payload_and_last_chunk_hits_total(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "apps" / "indexer" / "indexer" / "chunk.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "\n".join([f"line {idx}" for idx in range(1, 8)]) + "\n",
                encoding="utf-8",
            )

            payload = chunk_file(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=4,
                overlap=1,
                as_posix=True,
            )

            self.assertTrue(payload["pathIsRelative"])
            self.assertEqual(payload["path"], "apps/indexer/indexer/chunk.py")
            self.assertEqual(payload["totalLines"], 7)
            self.assertEqual(payload["encoding"], "utf-8")
            self.assertEqual(payload["warnings"], [])
            self.assertEqual(len(payload["chunks"]), 2)
            self.assertEqual(payload["chunks"][0]["startLine"], 1)
            self.assertEqual(payload["chunks"][0]["endLine"], 4)
            self.assertEqual(payload["chunks"][1]["startLine"], 4)
            self.assertEqual(payload["chunks"][1]["endLine"], 7)
            self.assertEqual(payload["chunks"][-1]["endLine"], payload["totalLines"])

            first_chunk = payload["chunks"][0]
            expected_content_hash = hash_content(
                "\n".join([f"line {idx}" for idx in range(1, 8)]) + "\n"
            )
            self.assertEqual(first_chunk["contentHash"], expected_content_hash)
            expected_chunk_id = make_chunk_id(
                payload["path"],
                first_chunk["startLine"],
                first_chunk["endLine"],
                first_chunk["contentHash"],
            )
            self.assertEqual(first_chunk["chunkId"], expected_chunk_id)

    def test_chunk_file_returns_warning_when_path_outside_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sandbox = Path(temp_dir)
            repo_root = sandbox / "repo"
            file_path = sandbox / "external.py"
            repo_root.mkdir()
            file_path.write_text("print('x')\n", encoding="utf-8")

            payload = chunk_file(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertFalse(payload["pathIsRelative"])
            self.assertEqual(len(payload["warnings"]), 1)
            self.assertIn("fora de REPO_ROOT", payload["warnings"][0])
            self.assertEqual(payload["chunks"][0]["path"], payload["path"])


if __name__ == "__main__":
    unittest.main()
