from __future__ import annotations

import unittest

from qdrant_client.http import models

from indexer.__main__ import _format_search_result_block
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
