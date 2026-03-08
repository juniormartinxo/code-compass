from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class MakefileChatTests(unittest.TestCase):
    def test_chat_installs_and_builds_mcp_server_when_bootstrap_is_missing(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        makefile = repo_root / "Makefile"

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            mcp_server_dir = workspace / "apps" / "mcp-server"
            bin_dir = workspace / "bin"
            log_file = workspace / "pnpm.log"

            mcp_server_dir.mkdir(parents=True)
            bin_dir.mkdir()
            (mcp_server_dir / "package.json").write_text("{}", encoding="utf-8")

            pnpm_stub = bin_dir / "pnpm"
            pnpm_stub.write_text(
                "\n".join(
                    [
                        "#!/bin/sh",
                        "set -eu",
                        'printf "%s\\n" "$*" >> "$PNPM_LOG"',
                        'if [ "$#" -ge 3 ] && [ "$1" = "-C" ] && [ "$3" = "install" ]; then',
                        '  mkdir -p "$2/node_modules"',
                        "  exit 0",
                        "fi",
                        'if [ "$#" -ge 4 ] && [ "$1" = "-C" ] && [ "$3" = "run" ] && [ "$4" = "build" ]; then',
                        '  mkdir -p "$2/dist"',
                        "  exit 0",
                        "fi",
                        'if [ "$#" -eq 1 ] && [ "$1" = "chat" ]; then',
                        "  exit 0",
                        "fi",
                        'echo "unexpected pnpm invocation: $*" >&2',
                        "exit 1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            pnpm_stub.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["PNPM_LOG"] = str(log_file)

            completed = subprocess.run(
                [
                    "make",
                    "-f",
                    str(makefile),
                    "chat",
                    f"MCP_SERVER_DIR={mcp_server_dir}",
                ],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertTrue((mcp_server_dir / "node_modules").is_dir())
            self.assertTrue((mcp_server_dir / "dist").is_dir())
            self.assertIn("Dependencias do MCP server ausentes; instalando...", completed.stdout)
            self.assertIn("Build do MCP server ausente; executando build...", completed.stdout)
            self.assertEqual(
                log_file.read_text(encoding="utf-8").splitlines(),
                [
                    f"-C {mcp_server_dir} install",
                    f"-C {mcp_server_dir} run build",
                    "chat",
                ],
            )


if __name__ == "__main__":
    unittest.main()
