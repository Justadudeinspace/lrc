"""Local Repo Compiler public API."""

from __future__ import annotations

__all__ = [
    "__version__",
    "Action",
    "BuildPlan",
    "ParseError",
    "compile_schema_path",
    "do_bootstrap",
    "get_default_output_dir",
    "parse_schema",
    "print_platform_info",
    "realize",
    "run_dat_audit",
]

__version__ = "1.0.0-alpha.1"

from .bootstrap import do_bootstrap
from .compiler import BuildPlan, compile_schema_path, get_default_output_dir, print_platform_info
from .generator import realize
from .integration import run_dat_audit
from .parser import Action, ParseError, parse_schema
