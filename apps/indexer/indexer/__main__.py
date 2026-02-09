from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ScanConfig, load_scan_config
from .scan import scan_repo


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m indexer")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Escaneia o repositório")
    scan_parser.add_argument("--repo-root", dest="repo_root", default=None)
    scan_parser.add_argument("--allow-exts", dest="allow_exts", default=None)
    scan_parser.add_argument("--ignore-dirs", dest="ignore_dirs", default=None)
    scan_parser.add_argument("--max-files", dest="max_files", type=int, default=None)

    return parser


def _resolve_scan_config(args: argparse.Namespace) -> ScanConfig:
    return load_scan_config(
        repo_root=args.repo_root,
        ignore_dirs=args.ignore_dirs,
        allow_exts=args.allow_exts,
    )


def _scan_command(args: argparse.Namespace) -> int:
    config = _resolve_scan_config(args)

    if not config.repo_root.exists() or not config.repo_root.is_dir():
        print(
            f"Erro: REPO_ROOT inválido ou inexistente: {config.repo_root}",
            file=sys.stderr,
        )
        return 1

    files, stats = scan_repo(
        repo_root=config.repo_root,
        ignore_dirs=config.ignore_dirs,
        allow_exts=config.allow_exts,
        max_files=args.max_files,
    )

    payload = {
        "repoRoot": str(config.repo_root),
        "ignoreDirs": sorted(config.ignore_dirs),
        "allowExts": sorted(config.allow_exts),
        "stats": stats,
        "files": [Path(path).as_posix() for path in files],
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        return _scan_command(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

