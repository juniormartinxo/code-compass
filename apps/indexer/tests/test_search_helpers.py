from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qdrant_client.http import models

from indexer.__main__ import (
    _build_search_header,
    _format_search_result_block,
    _normalize_snippet,
    _resolve_search_snippet,
)
from indexer.qdrant_store import build_qdrant_filter


class SearchOutputFormattingTests(unittest.TestCase):
    def test_format_search_result_block_uses_expected_layout(self) -> None:
        payload = {
            "path": "src/foo/bar.ts",
            "start_line": 120,
            "end_line": 168,
            "text": "linha 1\n\nlinha   2",
        }

        block = _format_search_result_block(
            index=1,
            score=0.78213,
            payload=payload,
        )

        self.assertIn("[1] score=0.7821  src/foo/bar.ts:120-168", block)
        self.assertIn('snippet: "linha 1 linha 2"', block)

    def test_format_search_result_block_without_text_payload(self) -> None:
        block = _format_search_result_block(
            index=2,
            score=0.55,
            payload={"path": "src/app.py", "start_line": 1, "end_line": 10},
        )

        self.assertIn('snippet: "(no text payload)"', block)

    def test_build_search_header_includes_repo_when_present(self) -> None:
        header = _build_search_header(
            {
                "repo": "analytics-portal",
                "path": "src/charts/drilldown.tsx",
                "start_line": 14,
                "end_line": 28,
            }
        )

        self.assertEqual(
            header,
            "[analytics-portal] src/charts/drilldown.tsx:14-28",
        )


class SearchSnippetFallbackTests(unittest.TestCase):
    def test_normalize_snippet_uses_env_limit(self) -> None:
        with patch.dict(os.environ, {"SEARCH_SNIPPET_MAX_CHARS": "20"}, clear=False):
            snippet = _normalize_snippet("abc " * 30)

        self.assertLessEqual(len(snippet), 20)
        self.assertTrue(snippet.endswith("..."))

    def test_resolve_search_snippet_uses_payload_text_when_available(self) -> None:
        snippet = _resolve_search_snippet(
            payload={
                "text": "const a = 1;",
                "repo_root": "/tmp/repo",
                "path": "src/main.ts",
                "start_line": 1,
                "end_line": 1,
            }
        )

        self.assertEqual(snippet, "const a = 1;")

    def test_resolve_search_snippet_falls_back_to_repo_file_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "src" / "components" / "drilldown.tsx"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(
                "line 1\nline 2\nline 3\nline 4\n",
                encoding="utf-8",
            )

            snippet = _resolve_search_snippet(
                payload={
                    "repo_root": str(repo_root),
                    "path": "src/components/drilldown.tsx",
                    "start_line": 2,
                    "end_line": 3,
                },
                line_cache={},
            )

        self.assertEqual(snippet, "line 2\nline 3")

    def test_resolve_search_snippet_returns_none_when_path_escapes_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)

            snippet = _resolve_search_snippet(
                payload={
                    "repo_root": str(repo_root),
                    "path": "../outside.txt",
                    "start_line": 1,
                    "end_line": 1,
                },
                line_cache={},
            )

        self.assertIsNone(snippet)


class SearchFilterBuilderTests(unittest.TestCase):
    def test_build_qdrant_filter_with_path_prefix_uses_match_text(self) -> None:
        query_filter = build_qdrant_filter({"path_prefix": "src/"})

        self.assertIsNotNone(query_filter)
        assert query_filter is not None
        self.assertEqual(len(query_filter.must), 1)

        condition = query_filter.must[0]
        assert isinstance(condition, models.FieldCondition)
        self.assertEqual(condition.key, "path")
        self.assertIsNotNone(condition.match)
        assert isinstance(condition.match, models.MatchText)
        self.assertEqual(condition.match.text, "src/")


if __name__ == "__main__":
    unittest.main()
