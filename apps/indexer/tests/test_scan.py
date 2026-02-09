from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from indexer.scan import scan_repo


class ScanRepoTests(unittest.TestCase):
    def test_scan_repo_applies_ignore_extension_and_binary_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src").mkdir()
            (repo_root / "node_modules" / "pkg").mkdir(parents=True)
            (repo_root / "dist").mkdir()

            (repo_root / "src" / "main.ts").write_text("const a = 1;\n", encoding="utf-8")
            (repo_root / "src" / "guide.md").write_text("# doc\n", encoding="utf-8")
            (repo_root / "src" / "binary.ts").write_bytes(b"bad\x00data")
            (repo_root / "src" / "image.png").write_bytes(b"PNG\x00DATA")
            (repo_root / "src" / "noext").write_text("sem extensao\n", encoding="utf-8")

            (repo_root / "node_modules" / "pkg" / "lib.js").write_text("module.exports = 1;\n", encoding="utf-8")
            (repo_root / "dist" / "bundle.ts").write_text("const dist = true;\n", encoding="utf-8")

            files, stats = scan_repo(
                repo_root=repo_root,
                ignore_dirs={"node_modules", "dist"},
                allow_exts={".ts", ".md"},
            )

            self.assertEqual([path.as_posix() for path in files], ["src/guide.md", "src/main.ts"])
            self.assertEqual(stats["total_dirs_seen"], 2)
            self.assertEqual(stats["dirs_ignored"], 2)
            self.assertEqual(stats["total_files_seen"], 5)
            self.assertEqual(stats["files_kept"], 2)
            self.assertEqual(stats["files_ignored_binary"], 1)
            self.assertEqual(stats["files_ignored_ext"], 2)
            self.assertGreaterEqual(stats["elapsed_ms"], 0)

    def test_scan_repo_max_files_limits_return_but_not_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src").mkdir()

            (repo_root / "src" / "a.ts").write_text("const a = 1;\n", encoding="utf-8")
            (repo_root / "src" / "b.ts").write_text("const b = 2;\n", encoding="utf-8")

            files, stats = scan_repo(
                repo_root=repo_root,
                ignore_dirs=set(),
                allow_exts={".ts"},
                max_files=1,
            )

            self.assertEqual(len(files), 1)
            self.assertEqual(stats["files_kept"], 2)


if __name__ == "__main__":
    unittest.main()

