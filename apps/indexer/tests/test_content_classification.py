from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch

from indexer.__main__ import (
    _build_classification_log_record,
    _classify_content_type,
    _resolve_collection_content_type,
)


class ContentClassificationTests(unittest.TestCase):
    def test_classifies_docs_by_extension(self) -> None:
        content_type, hint = _classify_content_type("README.md")
        self.assertEqual(content_type, "doc_section")
        self.assertEqual(_resolve_collection_content_type(content_type), "docs")
        self.assertEqual(hint, "/readme")

    def test_classifies_docs_by_path_hint(self) -> None:
        content_type, hint = _classify_content_type("apps/docs/api/auth.ts")
        self.assertEqual(content_type, "doc_section")
        self.assertEqual(_resolve_collection_content_type(content_type), "docs")
        self.assertEqual(hint, "/docs/")

    def test_classifies_code_for_regular_source_path(self) -> None:
        content_type, hint = _classify_content_type("src/services/auth.py")
        self.assertEqual(content_type, "code_context")
        self.assertEqual(_resolve_collection_content_type(content_type), "code")
        self.assertIsNone(hint)

    def test_classifies_tests_by_path_and_name(self) -> None:
        by_path, _ = _classify_content_type("tests/services/auth_service.py")
        by_name, _ = _classify_content_type("src/auth.spec.ts")

        self.assertEqual(by_path, "test_case")
        self.assertEqual(by_name, "test_case")
        self.assertEqual(_resolve_collection_content_type(by_path), "code")

    def test_classifies_config_and_sql_blocks(self) -> None:
        config_type, _ = _classify_content_type("infra/app/config.yaml")
        sql_type, _ = _classify_content_type("db/migrations/001_init.sql")

        self.assertEqual(config_type, "config_block")
        self.assertEqual(sql_type, "sql_block")
        self.assertEqual(_resolve_collection_content_type(config_type), "code")
        self.assertEqual(_resolve_collection_content_type(sql_type), "code")

    def test_does_not_classify_generic_structured_data_as_config(self) -> None:
        content_type, hint = _classify_content_type("fixtures/users.json")

        self.assertEqual(content_type, "code_context")
        self.assertEqual(_resolve_collection_content_type(content_type), "code")
        self.assertIsNone(hint)

    def test_rejects_unknown_chunk_content_type_for_collection_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported chunk content type"):
            _resolve_collection_content_type("unknown_type")

    def test_respects_doc_overrides_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DOC_EXTENSIONS": ".guide",
                "DOC_PATH_HINTS": "/manual/",
            },
            clear=False,
        ):
            by_extension, hint_extension = _classify_content_type("README.guide")
            by_hint, hint_path = _classify_content_type("pkg/manual/index.ts")

        self.assertEqual(by_extension, "doc_section")
        self.assertIsNone(hint_extension)
        self.assertEqual(by_hint, "doc_section")
        self.assertEqual(hint_path, "/manual/")

    def test_classification_log_record_has_expected_shape(self) -> None:
        record = _build_classification_log_record(
            file_path="docs/guide.md",
            ext=".md",
            path_hint="/docs/",
            classified_as="doc_section",
            collection_content_type="docs",
        )

        self.assertEqual(record["file"], "docs/guide.md")
        self.assertEqual(record["ext"], ".md")
        self.assertEqual(record["path_hint"], "/docs/")
        self.assertEqual(record["classified_as"], "doc_section")
        self.assertEqual(record["collection_content_type"], "docs")
        self.assertIn("ts", record)

        ts = str(record["ts"])
        parsed = datetime.fromisoformat(ts)
        self.assertIsNotNone(parsed.tzinfo)


if __name__ == "__main__":
    unittest.main()
