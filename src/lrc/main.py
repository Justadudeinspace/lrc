#!/usr/bin/env python3
"""LRC (Local Repo Compiler) CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .bootstrap import do_bootstrap
from .compiler import (
    check_fs_ok, 
    compile_schema_path, 
    print_platform_info, 
    resolve_output_directory
)
from .generator import realize, write_build_manifest
from .integration import run_dat_audit


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser for LRC."""
    parser = argparse.ArgumentParser(
        prog="lrc",
        description="Local Repo Compiler — Build repositories from declarative schemas",
        epilog="""
Examples:
  lrc schema.yaml                    # Generate project from schema
  lrc schema.yaml --out ./my-project # Specify output directory
  lrc schema.yaml --dry-run          # Preview without writing files
  lrc schema.yaml --audit            # Run security audit after generation
  lrc --bootstrap                    # Install LRC to user PATH
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Core arguments
    parser.add_argument(
        "schema", 
        nargs="?", 
        help="Path to the .lrc schema file (YAML or JSON)"
    )
    
    # Information and setup
    parser.add_argument(
        "--version", 
        action="version", 
        version=f"lrc {__version__}"
    )
    parser.add_argument(
        "--bootstrap", 
        action="store_true", 
        help="Install LRC into the user PATH"
    )
    parser.add_argument(
        "--platform-info",
        action="store_true",
        help="Print detected platform information and exit"
    )
    
    # Generation options
    parser.add_argument(
        "-o", "--out", 
        type=Path, 
        help="Output directory for generated project"
    )
    parser.add_argument(
        "-n", "--dry-run", 
        action="store_true", 
        help="Do not modify the filesystem, only show planned actions"
    )
    parser.add_argument(
        "-f", "--force", 
        action="store_true", 
        help="Overwrite existing files and directories"
    )
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Enable verbose logging"
    )
    
    # Audit integration
    audit_group = parser.add_argument_group('audit options')
    audit_group.add_argument(
        "--audit", 
        action="store_true", 
        help="Run DAT security audit after generation"
    )
    audit_group.add_argument(
        "--audit-out", 
        type=Path, 
        help="Path to write audit artifact"
    )
    audit_group.add_argument(
        "--audit-format",
        choices=["json", "pdf", "md", "combined"],
        default="json",
        help="Audit artifact format (default: %(default)s)"
    )
    audit_group.add_argument(
        "--audit-args", 
        default="",
        help="Additional arguments forwarded to DAT"
    )
    
    # Backwards compatibility
    parser.add_argument(
        "--audit-out-format",
        dest="audit_format",
        choices=["json", "pdf", "md", "combined"],
        help=argparse.SUPPRESS,  # Hidden for backwards compatibility
    )
    
    return parser


def validate_args(args: argparse.Namespace) -> tuple[bool, str]:
    """
    Validate command line arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check for conflicting audit format arguments
    if hasattr(args, 'audit_out_format') and args.audit_out_format:
        args.audit_format = args.audit_out_format
    
    # Validate schema file exists when required
    if args.schema and not Path(args.schema).exists():
        return False, f"schema file not found: {args.schema}"
    
    # Validate output directory permissions
    if args.out and args.out.exists() and not args.out.is_dir():
        return False, f"output path exists but is not a directory: {args.out}"
    
    return True, ""


def main(argv: Optional[list[str]] = None) -> int:
    """
    Main entry point for LRC CLI.
    
    Args:
        argv: Command line arguments (defaults to sys.argv[1:])
        
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    
    # Handle information commands first
    if args.platform_info:
        print_platform_info(verbose=args.verbose)
        return 0

    if args.bootstrap:
        try:
            target = do_bootstrap(sys.argv[0], verbose=args.verbose)
            print(f"✓ Installed LRC to {target}")
            return 0
        except Exception as e:
            print(f"✗ Bootstrap failed: {e}", file=sys.stderr)
            return 1

    # Validate arguments
    is_valid, error_msg = validate_args(args)
    if not is_valid:
        parser.error(error_msg)

    # Schema is required for generation commands
    if not args.schema:
        parser.error("a schema path is required unless using --platform-info or --bootstrap")

    schema_path = Path(args.schema)
    output_hint = args.out

    try:
        # Compile schema into execution plan
        plan = compile_schema_path(
            schema_path, 
            output_hint or Path.cwd(), 
            verbose=args.verbose
        )
    except FileNotFoundError:
        parser.error(f"schema file not found: {schema_path}")
    except Exception as exc:
        print(f"[ERROR] Failed to compile schema: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # Resolve output directory
    try:
        output_dir = resolve_output_directory(plan, output_hint)
        if output_dir != plan.root:
            plan = plan.rebase(output_dir)
    except Exception as exc:
        print(f"[ERROR] Failed to resolve output directory: {exc}", file=sys.stderr)
        return 2

    # Check filesystem permissions
    ok, reason = check_fs_ok(output_dir)
    if not ok:
        print(f"[ERROR] Output directory not writable: {reason}", file=sys.stderr)
        return 3

    if args.verbose:
        print(f"[PLAN] Generating project to: {output_dir}")
        print(f"[PLAN] Total operations: {len(plan.operations)}")

    # Execute generation plan
    try:
        result = realize(
            plan, 
            output_dir, 
            dry_run=args.dry_run, 
            force=args.force, 
            verbose=args.verbose
        )
    except Exception as exc:
        print(f"[ERROR] Generation failed: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 4

    # Run DAT audit if requested
    audit_summary = None
    if args.audit and not args.dry_run:
        if args.verbose:
            print("[AUDIT] Running security audit...")
        
        try:
            audit_summary = run_dat_audit(
                plan,
                output_dir,
                audit_out=args.audit_out,
                audit_format=args.audit_format,
                audit_args=args.audit_args,
                verbose=args.verbose,
            )
            
            if args.verbose and audit_summary:
                print(f"[AUDIT] Completed with {audit_summary.get('violations', 0)} violations")
                
        except Exception as exc:
            print(f"[WARNING] Audit failed: {exc}", file=sys.stderr)
            if args.verbose:
                import traceback
                traceback.print_exc()

    # Write build manifest
    try:
        manifest_path = write_build_manifest(
            plan, 
            output_dir, 
            dry_run=args.dry_run, 
            audit_summary=audit_summary
        )
        
        if args.verbose and manifest_path:
            print(f"[INFO] Build manifest written to: {manifest_path}")
            
    except Exception as exc:
        print(f"[WARNING] Failed to write build manifest: {exc}", file=sys.stderr)

    # Report results
    if args.verbose:
        if result.success:
            if args.dry_run:
                print("✓ Dry run completed successfully")
            else:
                print("✓ Project generation completed successfully")
        else:
            print("✗ Project generation completed with errors")

    return 0 if result.success else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
