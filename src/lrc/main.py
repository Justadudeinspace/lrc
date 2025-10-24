"""Command line interface for the Local Repo Compiler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .bootstrap import do_bootstrap
from .compiler import check_fs_ok, compile_schema_path, print_platform_info, resolve_output_directory
from .generator import realize, write_build_manifest
from .integration import run_dat_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lrc",
        description="Local Repo Compiler — build repositories from declarative schemas",
    )
    parser.add_argument("schema", nargs="?", help="Path to the .lrc schema file")
    parser.add_argument("--version", action="version", version=f"lrc {__version__}")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Do not modify the filesystem")
    parser.add_argument("-f", "--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("-o", "--out", type=Path, help="Output directory for generated project")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--audit", action="store_true", help="Run DAT audit after generation")
    parser.add_argument("--audit-out", type=Path, help="Path to write audit artifact")
    parser.add_argument(
        "--audit-format",
        choices=["json", "pdf", "md", "combined"],
        default="json",
        help="Audit artifact format",
    )
    parser.add_argument("--audit-args", default="", help="Additional arguments forwarded to DAT")
    parser.add_argument("--bootstrap", action="store_true", help="Install lrc into the user PATH")
    parser.add_argument(
        "--platform-info",
        action="store_true",
        help="Print detected platform information and exit",
    )
    parser.add_argument(
        "--audit-out-format",
        dest="audit_out_format",
        choices=["json", "pdf", "md", "combined"],
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.platform_info:
        print_platform_info(verbose=args.verbose)
        return 0

    if args.bootstrap:
        target = do_bootstrap(sys.argv[0], verbose=args.verbose)
        print(f"Installed lrc to {target}")
        return 0

    if not args.schema:
        parser.error("a schema path is required unless --platform-info or --bootstrap is used")

    schema_path = Path(args.schema)
    output_hint = args.out

    try:
        plan = compile_schema_path(schema_path, output_hint or Path.cwd(), verbose=args.verbose)
    except FileNotFoundError:
        parser.error(f"schema file not found: {schema_path}")
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    output_dir = resolve_output_directory(plan, output_hint)
    if output_dir != plan.root:
        plan = plan.rebase(output_dir)

    ok, reason = check_fs_ok(output_dir)
    if not ok:
        print(f"[ERROR] output directory not writable: {reason}")
        return 2

    if args.verbose:
        print(f"[PLAN] writing to {output_dir}")

    result = realize(plan, output_dir, dry_run=args.dry_run, force=args.force, verbose=args.verbose)

    audit_summary = None
    if args.audit and not args.dry_run:
        audit_summary = run_dat_audit(
            plan,
            output_dir,
            audit_out=args.audit_out,
            audit_format=args.audit_out_format or args.audit_format,
            audit_args=args.audit_args,
            verbose=args.verbose,
        )

    manifest_path = write_build_manifest(plan, output_dir, dry_run=args.dry_run, audit_summary=audit_summary)

    if args.verbose and manifest_path:
        print(f"[INFO] wrote manifest to {manifest_path}")

    return 0 if result.success else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
