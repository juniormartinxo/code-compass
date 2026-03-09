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
from indexer.chunk_models import (
    CHUNK_SCHEMA_VERSION,
    IndexedChunk,
    LINE_WINDOW_CHUNK_STRATEGY,
    PYTHON_SYMBOL_CHUNK_STRATEGY,
    TS_SYMBOL_CHUNK_STRATEGY,
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

        anchored_symbol = make_chunk_id(
            "apps/indexer/file.py",
            10,
            20,
            "python",
            qualified_symbol_name="Service.run",
            symbol_type="method",
        )
        moved_symbol = make_chunk_id(
            "apps/indexer/file.py",
            30,
            40,
            "python",
            qualified_symbol_name="Service.run",
            symbol_type="method",
        )
        renamed_symbol = make_chunk_id(
            "apps/indexer/file.py",
            30,
            40,
            "python",
            qualified_symbol_name="Service.execute",
            symbol_type="method",
        )

        self.assertEqual(anchored_symbol, moved_symbol)
        self.assertNotEqual(anchored_symbol, renamed_symbol)

        property_getter = make_chunk_id(
            "apps/indexer/file.py",
            10,
            20,
            "python",
            qualified_symbol_name="Service.value",
            symbol_type="method",
            signature="def value(self) -> str:",
        )
        property_setter = make_chunk_id(
            "apps/indexer/file.py",
            21,
            30,
            "python",
            qualified_symbol_name="Service.value",
            symbol_type="method",
            signature="def value(self, new_value: str) -> None:",
        )

        self.assertNotEqual(property_getter, property_setter)

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
            self.assertEqual(first_chunk["contentType"], "code_context")
            self.assertEqual(first_chunk["collectionContentType"], "code")
            self.assertEqual(
                first_chunk["summaryText"],
                (
                    "apps/indexer/indexer/chunk.py | python | lines 1-4 | type=code_context "
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

            self.assertEqual(len(result.chunks), 1)
            chunk = result.chunks[0]
            self.assertEqual(chunk.startLine, 3)
            self.assertEqual(chunk.endLine, 4)
            self.assertEqual(chunk.contentType, "code_symbol")
            self.assertEqual(chunk.chunkStrategy, PYTHON_SYMBOL_CHUNK_STRATEGY)
            self.assertEqual(chunk.symbolName, "load_data")
            self.assertEqual(chunk.qualifiedSymbolName, "load_data")
            self.assertEqual(chunk.symbolType, "function")
            self.assertEqual(
                chunk.summaryText,
                (
                    "src/service.py | python | lines 3-4 | type=code_symbol | symbol=load_data "
                    "| symbol_type=function "
                    "| first_line=def load_data(user_id: str) -> dict[str, str]:"
                ),
            )
            self.assertIn("Chunk strategy: python_symbol", chunk.contextText)
            self.assertIn("Symbol: load_data", chunk.contextText)
            self.assertIn("Symbol type: function", chunk.contextText)
            self.assertIn(
                "Signature: def load_data(user_id: str) -> dict[str, str]:",
                chunk.contextText,
            )
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
        self.assertEqual(payload["chunk_strategy"], document.chunkStrategy)
        self.assertEqual(payload["content_type"], document.collectionContentType)
        self.assertEqual(payload["chunk_content_type"], document.contentType)
        self.assertEqual(payload["start_line"], document.startLine)
        self.assertEqual(payload["end_line"], document.endLine)
        self.assertEqual(payload["text"], document.content)
        self.assertEqual(payload["summary_text"], document.summaryText)
        self.assertEqual(payload["context_text"], document.contextText)

    def test_chunk_file_keeps_symbol_chunk_id_stable_when_lines_shift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "service.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "def load_data(user_id: str) -> dict[str, str]:\n"
                "    return {'id': user_id}\n",
                encoding="utf-8",
            )

            initial = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            file_path.write_text(
                "# comment added above\n\n"
                "def load_data(user_id: str) -> dict[str, str]:\n"
                "    return {'id': user_id}\n",
                encoding="utf-8",
            )

            updated = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(len(initial.chunks), 1)
            self.assertEqual(len(updated.chunks), 2)
            updated_symbol = next(chunk for chunk in updated.chunks if chunk.symbolName == "load_data")
            context_chunk = next(chunk for chunk in updated.chunks if chunk.symbolName is None)

            self.assertEqual(initial.chunks[0].chunkId, updated_symbol.chunkId)
            self.assertNotEqual(initial.chunks[0].startLine, updated_symbol.startLine)
            self.assertEqual(context_chunk.contentType, "code_context")
            self.assertIn("# comment added above", context_chunk.content)

    def test_chunk_file_falls_back_to_line_window_when_python_parse_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "broken.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "def broken(\n"
                "    return 1\n",
                encoding="utf-8",
            )

            result = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(len(result.chunks), 1)
            chunk = result.chunks[0]
            self.assertEqual(chunk.chunkStrategy, LINE_WINDOW_CHUNK_STRATEGY)
            self.assertEqual(chunk.contentType, "code_context")
            self.assertIsNone(chunk.symbolName)
            self.assertIn("def broken(", chunk.content)

    def test_chunk_file_uses_ts_symbol_strategy_for_valid_tsx_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "components" / "product-card.tsx"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "import { api } from './api';\n\n"
                "export const useProduct = (id: string) => {\n"
                "  return api.load(id);\n"
                "};\n\n"
                "export function ProductCard({ title }: { title: string }) {\n"
                "  return <section>{title}</section>;\n"
                "}\n",
                encoding="utf-8",
            )

            result = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(len(result.chunks), 3)
            import_chunk = result.chunks[0]
            hook_chunk = result.chunks[1]
            component_chunk = result.chunks[2]

            self.assertEqual(import_chunk.contentType, "code_context")
            self.assertEqual(hook_chunk.chunkStrategy, TS_SYMBOL_CHUNK_STRATEGY)
            self.assertEqual(hook_chunk.contentType, "code_symbol")
            self.assertEqual(hook_chunk.collectionContentType, "code")
            self.assertEqual(hook_chunk.symbolName, "useProduct")
            self.assertEqual(hook_chunk.symbolType, "hook")
            self.assertEqual(hook_chunk.imports, ("./api",))
            self.assertEqual(hook_chunk.exports, ("useProduct", "ProductCard"))
            self.assertEqual(hook_chunk.callers, ())
            self.assertEqual(hook_chunk.callees, ("api.load",))
            self.assertIn("Signature: export const useProduct = (id: string) =>", hook_chunk.contextText)

            self.assertEqual(component_chunk.symbolName, "ProductCard")
            self.assertEqual(component_chunk.symbolType, "component")
            self.assertEqual(component_chunk.callers, ())
            self.assertEqual(component_chunk.callees, ())
            self.assertIn("<section>{title}</section>", component_chunk.content)

    def test_chunk_file_keeps_ts_symbol_chunk_id_stable_when_lines_shift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "service.ts"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "export const loadData = (id: string) => {\n"
                "  return id;\n"
                "};\n",
                encoding="utf-8",
            )

            initial = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            file_path.write_text(
                "// comment added above\n\n"
                "export const loadData = (id: string) => {\n"
                "  return id;\n"
                "};\n",
                encoding="utf-8",
            )

            updated = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(len(initial.chunks), 1)
            self.assertEqual(len(updated.chunks), 2)

            updated_symbol = next(chunk for chunk in updated.chunks if chunk.symbolName == "loadData")
            context_chunk = next(chunk for chunk in updated.chunks if chunk.symbolName is None)

            self.assertEqual(initial.chunks[0].chunkId, updated_symbol.chunkId)
            self.assertNotEqual(initial.chunks[0].startLine, updated_symbol.startLine)
            self.assertEqual(updated_symbol.chunkStrategy, TS_SYMBOL_CHUNK_STRATEGY)
            self.assertIn("// comment added above", context_chunk.content)

    def test_chunk_file_keeps_anonymous_default_ts_export_chunk_id_stable_when_lines_shift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "components" / "product-card.tsx"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "export default () => <section />;\n",
                encoding="utf-8",
            )

            initial = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            file_path.write_text(
                "// comment added above\n"
                "export default () => <section />;\n",
                encoding="utf-8",
            )

            updated = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(len(initial.chunks), 1)
            self.assertEqual(len(updated.chunks), 2)

            updated_symbol = next(chunk for chunk in updated.chunks if chunk.symbolName == "default")
            context_chunk = next(chunk for chunk in updated.chunks if chunk.symbolName is None)

            self.assertEqual(initial.chunks[0].chunkId, updated_symbol.chunkId)
            self.assertEqual(updated_symbol.chunkStrategy, TS_SYMBOL_CHUNK_STRATEGY)
            self.assertEqual(updated_symbol.symbolType, "component")
            self.assertIn("// comment added above", context_chunk.content)

    def test_chunk_file_falls_back_to_line_window_when_ts_parse_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "broken.ts"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "export const broken = () => {\n"
                "  return 1;\n",
                encoding="utf-8",
            )

            result = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=10,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(len(result.chunks), 1)
            chunk = result.chunks[0]
            self.assertEqual(chunk.chunkStrategy, LINE_WINDOW_CHUNK_STRATEGY)
            self.assertEqual(chunk.contentType, "code_context")
            self.assertIsNone(chunk.symbolName)
            self.assertIn("export const broken", chunk.content)

    def test_indexed_chunk_serializes_doc_payload_to_docs_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "docs" / "guide.md"
            file_path.parent.mkdir(parents=True)
            file_path.write_text("# Guide\n\nHello\n", encoding="utf-8")

            document = chunk_file_documents(
                file_path=file_path,
                repo_root=repo_root,
                chunk_lines=20,
                overlap=0,
                as_posix=True,
            ).chunks[0]
            indexed = IndexedChunk(
                document=document,
                chunkIndex=0,
                fileMtime=123.0,
                fileSize=file_path.stat().st_size,
            )

            payload = indexed.to_qdrant_payload(
                repo="indexer",
                repo_root=repo_root,
            )

            self.assertEqual(document.contentType, "doc_section")
            self.assertEqual(document.collectionContentType, "docs")
            self.assertEqual(payload["content_type"], "docs")
            self.assertEqual(payload["chunk_content_type"], "doc_section")

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

            self.assertEqual(result.chunks[0].contentType, "doc_section")
            self.assertEqual(result.chunks[0].collectionContentType, "docs")

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

            self.assertEqual(result.chunks[0].contentType, "doc_section")
            self.assertEqual(result.chunks[0].collectionContentType, "docs")

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

            self.assertEqual(result.chunks[0].contentType, "doc_section")
            self.assertEqual(result.chunks[0].collectionContentType, "docs")

    def test_chunk_file_classifies_test_and_config_blocks_as_code_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            test_file = repo_root / "tests" / "service.spec.ts"
            config_file = repo_root / "infra" / "settings.yaml"
            test_file.parent.mkdir(parents=True)
            config_file.parent.mkdir(parents=True)
            test_file.write_text("export const ok = true;\n", encoding="utf-8")
            config_file.write_text("debug: true\n", encoding="utf-8")

            test_result = chunk_file_documents(
                file_path=test_file,
                repo_root=repo_root,
                chunk_lines=20,
                overlap=0,
                as_posix=True,
            )
            config_result = chunk_file_documents(
                file_path=config_file,
                repo_root=repo_root,
                chunk_lines=20,
                overlap=0,
                as_posix=True,
            )

            self.assertEqual(test_result.chunks[0].contentType, "test_case")
            self.assertEqual(test_result.chunks[0].collectionContentType, "code")
            self.assertEqual(config_result.chunks[0].contentType, "config_block")
            self.assertEqual(config_result.chunks[0].collectionContentType, "code")


if __name__ == "__main__":
    unittest.main()
