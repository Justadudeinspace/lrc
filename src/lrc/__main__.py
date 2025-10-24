#!/usr/bin/env python3
"""
LRC (Local Repo Compiler) - Module entry point for ``python -m lrc``.

This module provides the entry point when LRC is executed as a module:
    python -m lrc [ARGS]

It handles proper initialization, error handling, and clean shutdown.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import NoReturn


def setup_environment() -> None:
    """
    Set up the runtime environment for LRC.
    
    This function:
    - Ensures proper UTF-8 encoding
    - Sets up Python path if needed
    - Configures environment variables
    """
    # Ensure UTF-8 encoding for cross-platform compatibility
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except (AttributeError, Exception):
            # Fallback for older Python versions
            pass
    
    if sys.stderr.encoding.lower() != 'utf-8':
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except (AttributeError, Exception):
            # Fallback for older Python versions
            pass
    
    # Add current directory to Python path for development
    if str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))
    
    # Set environment variables for consistent behavior
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    os.environ.setdefault('LRC_FORCE_COLOR', '0')


def handle_import_error() -> NoReturn:
    """
    Handle import errors with helpful error messages.
    
    This provides guidance for common installation and setup issues.
    """
    print("Error: Could not import LRC modules.", file=sys.stderr)
    print("\nThis usually indicates:", file=sys.stderr)
    print("  1. LRC is not properly installed", file=sys.stderr)
    print("  2. You're running from the wrong directory", file=sys.stderr)
    print("  3. There's a missing dependency", file=sys.stderr)
    print("\nTroubleshooting steps:", file=sys.stderr)
    print("  - Install with: pip install -e .", file=sys.stderr)
    print("  - Run from project root directory", file=sys.stderr)
    print("  - Check Python path and virtual environment", file=sys.stderr)
    
    # Debug information
    print(f"\nDebug info:", file=sys.stderr)
    print(f"  Python: {sys.version}", file=sys.stderr)
    print(f"  Executable: {sys.executable}", file=sys.stderr)
    print(f"  Current dir: {Path.cwd()}", file=sys.stderr)
    print(f"  Python path: {sys.path}", file=sys.stderr)
    
    sys.exit(1)


def main() -> int:
    """
    Main entry point for module execution.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    try:
        # Set up environment before importing LRC modules
        setup_environment()
        
        # Import the main CLI function
        try:
            from .cli import main as cli_main
        except ImportError as e:
            print(f"Import error: {e}", file=sys.stderr)
            handle_import_error()
        
        # Execute the CLI with command line arguments
        return cli_main()
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130  # Standard exit code for SIGINT
        
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        
        # Provide debug information for unexpected errors
        if os.environ.get('LRC_DEBUG'):
            import traceback
            traceback.print_exc()
            
        return 1


if __name__ == "__main__":
    # Ensure clean exit with proper exit code
    exit_code = main()
    sys.exit(exit_code)
