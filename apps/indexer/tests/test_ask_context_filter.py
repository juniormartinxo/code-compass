from __future__ import annotations

import unittest

from indexer.__main__ import _filter_context_results, _should_exclude_context_path


class AskContextFilterTests(unittest.TestCase):
    def test_should_exclude_known_environment_paths(self) -> None:
        self.assertTrue(_should_exclude_context_path("apps/indexer/.venv/lib/python3.12/site-packages/pkg.py"))
        self.assertTrue(_should_exclude_context_path("apps/indexer/venv/lib/python3.12/site-packages/pkg.py"))
        self.assertTrue(_should_exclude_context_path("src/__pycache__/module.cpython-312.pyc"))
        self.assertTrue(_should_exclude_context_path(".pytest_cache/v/cache/nodeids"))

    def test_should_not_exclude_regular_project_paths(self) -> None:
        self.assertFalse(_should_exclude_context_path("apps/indexer/indexer/__main__.py"))
        self.assertFalse(_should_exclude_context_path("docs/indexer/commands/ask.md"))
        self.assertFalse(_should_exclude_context_path(None))

    def test_filter_context_results_excludes_environment_paths(self) -> None:
        results = [
            {
                "id": "1",
                "score": 0.95,
                "payload": {
                    "path": "apps/indexer/.venv/lib/python3.12/site-packages/idna/idnadata.py",
                },
            },
            {
                "id": "2",
                "score": 0.93,
                "payload": {
                    "path": "apps/indexer/indexer/__main__.py",
                },
            },
        ]

        filtered, excluded = _filter_context_results(results)

        self.assertEqual(excluded, 1)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "2")


if __name__ == "__main__":
    unittest.main()
