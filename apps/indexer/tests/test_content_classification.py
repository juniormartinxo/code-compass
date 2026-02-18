from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch

from indexer.__main__ import _build_classification_log_record, _classify_content_type


class ContentClassificationTests(unittest.TestCase):
    def test_classifies_docs_by_extension(self) -> None:
        content_type, hint = _classify_content_type("README.md")
        self.assertEqual(content_type, "docs")
        self.assertEqual(hint, "/readme")

    def test_classifies_docs_by_path_hint(self) -> None:
        content_type, hint = _classify_content_type("apps/docs/api/auth.ts")
        self.assertEqual(content_type, "docs")
        self.assertEqual(hint, "/docs/")

    def test_classifies_code_for_regular_source_path(self) -> None:
        content_type, hint = _classify_content_type("src/services/auth.py")
        self.assertEqual(content_type, "code")
        self.assertIsNone(hint)

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

        self.assertEqual(by_extension, "docs")
        self.assertIsNone(hint_extension)
        self.assertEqual(by_hint, "docs")
        self.assertEqual(hint_path, "/manual/")

    def test_classification_log_record_has_expected_shape(self) -> None:
        record = _build_classification_log_record(
            file_path="docs/guide.md",
            ext=".md",
            path_hint="/docs/",
            classified_as="docs",
        )

        self.assertEqual(record["file"], "docs/guide.md")
        self.assertEqual(record["ext"], ".md")
        self.assertEqual(record["path_hint"], "/docs/")
        self.assertEqual(record["classified_as"], "docs")
        self.assertIn("ts", record)

        ts = str(record["ts"])
        parsed = datetime.fromisoformat(ts)
        self.assertIsNotNone(parsed.tzinfo)


if __name__ == "__main__":
    unittest.main()
