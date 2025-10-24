"""Command line interface for LRC."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .. import core
from ..audit import run_dat_audit
from ..parser import ParseError, parse_schema
from ..compiler import realize

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def colorize(message: str, color: str) -> str:
    if not sys.stdout.isatty():
        return message
    return f"{color}{message}{RESET}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="lrc — Local Repo Compile — Build a local repo from a declarative text schema.",
        epilog="""Examples:\n  lrc schema.txt --dry-run\n  lrc schema.txt --audit\n  lrc --bootstrap""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("schema", nargs="?", help="Input schema file")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument(
        "--base-dir", help="Base directory for includes (default: schema file dir)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be created"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument(
        "--audit", action="store_true", help="Run DAT audit after successful build"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--bootstrap", action="store_true", help="Install lrc to user bin directory"
    )
    parser.add_argument(
        "--platform-info", action="store_true", help="Show platform information"
    )
    parser.add_argument(
        "--version", action="store_true", help="Show version information"
    )
    return parser


def _display_metadata(meta: dict) -> None:
    if meta.get("Project") or meta.get("Description"):
        print(colorize("\n[PROJECT]", CYAN))
        for key in ["Project", "Description", "Version"]:
            if meta.get(key):
                print(f"  {key}: {meta[key]}")
        print()


def _print_error_context(path: Path, line_num: int, message: str, snippet: str) -> None:
    pointer = colorize("--> ", RED)
    print(colorize(f"[PARSE ERROR] {message}", RED))
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
    else:
        lines = []
    if 1 <= line_num <= len(lines):
        context = lines[line_num - 1]
        print(f"{pointer}{path}:{line_num}: {context}")
        if snippet:
            print(f"    {snippet}")
    elif snippet:
        print(f"{pointer}{snippet}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"lrc version {core.__version__}")
        return 0

    if args.platform_info:
        core.print_platform_info(verbose=True)
        return 0

    if args.bootstrap:
        core.do_bootstrap(sys.argv[0], verbose=args.verbose)
        return 0

    if not args.schema:
        parser.print_help()
        print(colorize("\n[ERROR] No schema file specified", RED))
        return 1

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(colorize(f"[ERROR] Schema file not found: {schema_path}", RED))
        return 1

    base_dir = Path(args.base_dir) if args.base_dir else schema_path.parent
    base_dir = base_dir.resolve()

    if args.output:
        out_root = Path(args.output).resolve()
    else:
        schema_text = schema_path.read_text(encoding="utf-8")
        project_name = None
        for line in schema_text.splitlines():
            if line.strip().lower().startswith("# project:"):
                project_name = line.split(":", 1)[1].strip()
                break
        out_root = core.get_default_output_dir(project_name)

    fs_ok, fs_msg = core.check_fs_ok(out_root)
    if not fs_ok:
        print(colorize(f"[ERROR] Filesystem issue: {fs_msg}", RED))
        return 1

    if args.verbose:
        core.print_platform_info()
        print(f"[INFO] Schema: {schema_path}")
        print(f"[INFO] Base dir: {base_dir}")
        print(f"[INFO] Output: {out_root}")
        print(f"[INFO] Force: {args.force}")
        print(f"[INFO] Dry run: {args.dry_run}")
        print(f"[INFO] Audit: {args.audit}")

    try:
        schema_text = schema_path.read_text(encoding="utf-8")
        actions, meta, vars_ = parse_schema(
            schema_text, out_root, base_dir, args.verbose
        )
        _display_metadata(meta)

        print(colorize(f"[BUILD] Creating repository in {out_root}", CYAN))
        success = realize(actions, out_root, args.dry_run, args.force, args.verbose)

        if not success:
            print(colorize("[ERROR] Some operations failed", RED))
            return 1

        if args.dry_run:
            print(
                colorize(
                    f"[SUCCESS] Dry run completed - would create {len(actions)} actions",
                    GREEN,
                )
            )
            return 0

        print(colorize(f"[SUCCESS] Repository created: {out_root}", GREEN))

        if args.audit:
            try:
                run_dat_audit(out_root)
            except Exception as exc:  # pragma: no cover - unexpected env issues
                print(colorize(f"[AUDIT] Failed: {exc}", YELLOW))
        return 0
    except ParseError as err:
        _print_error_context(schema_path, err.line_num, err.message, err.line_content)
        return 2
    except Exception as exc:  # pragma: no cover - defensive programming
        print(colorize(f"[ERROR] {exc}", RED))
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


__all__ = ["build_parser", "main"]
