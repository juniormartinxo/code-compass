from __future__ import annotations

from dataclasses import replace
import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from indexer.chunk import (
    chunk_file,
    chunk_file_documents,
    chunk_lines,
    detect_language,
    hash_content,
    make_chunk_id,
    normalize_path,
    read_text,
)
from indexer.chunk_models import CHUNK_SCHEMA_VERSION, IndexedChunk, LINE_WINDOW_CHUNK_STRATEGY


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

    def test_hash_and_chunk_id_are_stable_for_structure(self) -> None:
        content = "alpha\r\nbeta\r\n"
        expected_hash = hashlib.sha256("alpha\nbeta\n".encode("utf-8")).hexdigest()
        content_hash = hash_content(content)

        self.assertEqual(content_hash, expected_hash)

        chunk_id = make_chunk_id("apps/indexer/file.py", 1, 2, "python")
        same_chunk_id = make_chunk_id("apps/indexer/file.py", 1, 2, "python")
        different_path = make_chunk_id("apps/indexer/other.py", 1, 2, "python")
        different_range = make_chunk_id("apps/indexer/file.py", 2, 2, "python")
        different_language = make_chunk_id("apps/indexer/file.py", 1, 2, "markdown")

        self.assertEqual(chunk_id, same_chunk_id)
        self.assertNotEqual(chunk_id, different_path)
        self.assertNotEqual(chunk_id, different_range)
        self.assertNotEqual(chunk_id, different_language)

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
                "\n".join([f"line {idx}" for idx in range(1, 5)])
            )
            self.assertEqual(first_chunk["contentHash"], expected_content_hash)
            self.assertEqual(first_chunk["chunkSchemaVersion"], CHUNK_SCHEMA_VERSION)
            self.assertEqual(first_chunk["chunkStrategy"], LINE_WINDOW_CHUNK_STRATEGY)
            self.assertEqual(first_chunk["contentType"], "code")
            self.assertEqual(
                first_chunk["summaryText"],
                (
                    "apps/indexer/indexer/chunk.py | python | lines 1-4 | type=code "
                    "| first_line=line 1"
                ),
            )
            self.assertIn("Path: apps/indexer/indexer/chunk.py", first_chunk["contextText"])
            self.assertIn("Preview: line 1 line 2 line 3 line 4", first_chunk["contextText"])
            expected_chunk_id = make_chunk_id(
                payload["path"],
                first_chunk["startLine"],
                first_chunk["endLine"],
                first_chunk["language"],
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

    def test_chunk_file_keeps_chunk_id_stable_when_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "module.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text("line 1\nline 2\nline 3\nline 4\n", encoding="utf-8")

            initial = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=4,
                overlap=0,
                as_posix=True,
            )

            file_path.write_text("line 1\nline 2 changed\nline 3\nline 4\n", encoding="utf-8")

            updated = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=4,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(initial.chunks[0].chunkId, updated.chunks[0].chunkId)
            self.assertNotEqual(initial.chunks[0].contentHash, updated.chunks[0].contentHash)

    def test_chunk_file_populates_summary_and_context_from_first_useful_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "service.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "\n\n"
                "def load_data(user_id: str) -> dict[str, str]:\n"
                "    return {'id': user_id}\n",
                encoding="utf-8",
            )

            result = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            chunk = result.chunks[0]
            self.assertEqual(
                chunk.summaryText,
                (
                    "src/service.py | python | lines 1-4 | type=code "
                    "| first_line=def load_data(user_id: str) -> dict[str, str]:"
                ),
            )
            self.assertIn("Chunk strategy: line_window", chunk.contextText)
            self.assertNotIn("Summary:", chunk.contextText)
            self.assertIn(
                "Preview: def load_data(user_id: str) -> dict[str, str]: return {'id': user_id}",
                chunk.contextText,
            )

    def test_indexed_chunk_serializes_qdrant_payload_with_schema_metadata(self) -> None:
        document = chunk_file_documents(
            file_path=Path(__file__),
            repo_root=Path(__file__).resolve().parents[1],
            chunk_lines=40,
            overlap=0,
            as_posix=True,
        ).chunks[0]
        indexed = IndexedChunk(
            document=document,
            chunkIndex=0,
            fileMtime=123.0,
            fileSize=456,
        )

        payload = indexed.to_qdrant_payload(
            repo="indexer",
            repo_root=Path(__file__).resolve().parents[1],
        )

        self.assertEqual(payload["chunk_id"], document.chunkId)
        self.assertEqual(payload["content_hash"], document.contentHash)
        self.assertEqual(payload["chunk_schema_version"], CHUNK_SCHEMA_VERSION)
        self.assertEqual(payload["chunk_strategy"], LINE_WINDOW_CHUNK_STRATEGY)
        self.assertEqual(payload["content_type"], "code")
        self.assertEqual(payload["start_line"], document.startLine)
        self.assertEqual(payload["end_line"], document.endLine)
        self.assertEqual(payload["text"], document.content)
        self.assertEqual(payload["summary_text"], document.summaryText)
        self.assertEqual(payload["context_text"], document.contextText)

    def test_chunk_document_to_dict_serializes_tuple_fields_as_lists(self) -> None:
        document = chunk_file_documents(
            file_path=Path(__file__),
            repo_root=Path(__file__).resolve().parents[1],
            chunk_lines=40,
            overlap=0,
            as_posix=True,
        ).chunks[0]
        enriched = replace(
            document,
            imports=("a", "b"),
            exports=("c",),
            callers=("d",),
            callees=("e",),
        )

        serialized = enriched.to_dict()

        self.assertEqual(serialized["imports"], ["a", "b"])
        self.assertEqual(serialized["exports"], ["c"])
        self.assertEqual(serialized["callers"], ["d"])
        self.assertEqual(serialized["callees"], ["e"])

    def test_indexed_chunk_generates_uuid_point_id_from_chunk_id(self) -> None:
        document = chunk_file_documents(
            file_path=Path(__file__),
            repo_root=Path(__file__).resolve().parents[1],
            chunk_lines=40,
            overlap=0,
            as_posix=True,
        ).chunks[0]
        indexed = IndexedChunk(
            document=document,
            chunkIndex=0,
            fileMtime=123.0,
            fileSize=456,
        )
        repo_root = Path(__file__).resolve().parents[1]

        point_id = indexed.point_id(repo="indexer", repo_root=repo_root)

        self.assertEqual(
            point_id,
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"indexer:{repo_root}:{document.chunkId}",
                )
            ),
        )
        self.assertEqual(
            indexed.to_qdrant_point(
                repo="indexer",
                repo_root=repo_root,
                vector=[0.1, 0.2],
            )["id"],
            point_id,
        )

    def test_indexed_chunk_point_id_differs_between_repo_roots_with_same_repo_name(self) -> None:
        document = chunk_file_documents(
            file_path=Path(__file__),
            repo_root=Path(__file__).resolve().parents[1],
            chunk_lines=40,
            overlap=0,
            as_posix=True,
        ).chunks[0]
        indexed = IndexedChunk(
            document=document,
            chunkIndex=0,
            fileMtime=123.0,
            fileSize=456,
        )

        first = indexed.point_id(
            repo="shared-lib",
            repo_root=Path("/tmp/codebase-a/shared-lib"),
        )
        second = indexed.point_id(
            repo="shared-lib",
            repo_root=Path("/tmp/codebase-b/shared-lib"),
        )

        self.assertNotEqual(first, second)

    def test_chunk_file_classifies_doc_like_paths_as_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "docs" / "config.json"
            file_path.parent.mkdir(parents=True)
            file_path.write_text('{"name":"guide"}\n', encoding="utf-8")

            result = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=20,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(result.chunks[0].contentType, "docs")

    def test_chunk_file_respects_runtime_doc_extension_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "README.guide"
            file_path.write_text("custom docs\n", encoding="utf-8")

            with mock.patch.dict("os.environ", {"DOC_EXTENSIONS": ".guide"}, clear=False):
                result = chunk_file_documents(
                    file_path=file_path,
                    repo_root=repo_root,
                    chunk_lines=20,
                    overlap=0,
                    as_posix=True,
                )

            self.assertEqual(result.chunks[0].contentType, "docs")

    def test_chunk_file_respects_runtime_doc_path_hint_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "pkg" / "manual" / "index.ts"
            file_path.parent.mkdir(parents=True)
            file_path.write_text("export const guide = true;\n", encoding="utf-8")

            with mock.patch.dict("os.environ", {"DOC_PATH_HINTS": "/manual/"}, clear=False):
                result = chunk_file_documents(
                    file_path=file_path,
                    repo_root=repo_root,
                    chunk_lines=20,
                    overlap=0,
                    as_posix=True,
                )

            self.assertEqual(result.chunks[0].contentType, "docs")


if __name__ == "__main__":
    unittest.main()
