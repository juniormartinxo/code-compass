from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .chunk import chunk_file
from .config import ChunkConfig, ScanConfig, load_chunk_config, load_scan_config
from .scan import scan_repo


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m indexer")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Escaneia o repositório")
    scan_parser.add_argument("--repo-root", dest="repo_root", default=None)
    scan_parser.add_argument("--allow-exts", dest="allow_exts", default=None)
    scan_parser.add_argument("--ignore-dirs", dest="ignore_dirs", default=None)
    scan_parser.add_argument("--max-files", dest="max_files", type=int, default=None)

    chunk_parser = subparsers.add_parser("chunk", help="Gera chunks de um arquivo")
    chunk_parser.add_argument("--file", dest="file", required=True)
    chunk_parser.add_argument("--chunk-lines", dest="chunk_lines", type=int, default=None)
    chunk_parser.add_argument("--overlap-lines", dest="overlap_lines", type=int, default=None)
    chunk_parser.add_argument("--repo-root", dest="repo_root", default=None)
    chunk_parser.add_argument(
        "--as-posix",
        dest="as_posix",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    return parser


def _resolve_scan_config(args: argparse.Namespace) -> ScanConfig:
    return load_scan_config(
        repo_root=args.repo_root,
        ignore_dirs=args.ignore_dirs,
        allow_exts=args.allow_exts,
    )


def _resolve_chunk_config(args: argparse.Namespace) -> ChunkConfig:
    return load_chunk_config(
        repo_root=args.repo_root,
        chunk_lines=args.chunk_lines,
        overlap_lines=args.overlap_lines,
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


def _chunk_command(args: argparse.Namespace) -> int:
    try:
        config = _resolve_chunk_config(args)
        result = chunk_file(
            file_path=Path(args.file),
            repo_root=config.repo_root,
            chunk_lines=config.chunk_lines,
            overlap=config.overlap_lines,
            as_posix=args.as_posix,
        )
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    payload = {
        "file": str(Path(args.file).expanduser().resolve()),
        "repoRoot": str(config.repo_root),
        "path": result["path"],
        "pathIsRelative": result["pathIsRelative"],
        "asPosix": args.as_posix,
        "chunkLines": config.chunk_lines,
        "overlapLines": config.overlap_lines,
        "totalLines": result["totalLines"],
        "encoding": result["encoding"],
        "chunks": result["chunks"],
        "stats": {"chunks": len(result["chunks"])},
        "warnings": result["warnings"],
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        return _scan_command(args)
    if args.command == "chunk":
        return _chunk_command(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
