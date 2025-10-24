"""
LRC - Local Repo Compile
Build local repositories from declarative text schemas.
"""

__version__ = "1.0.0-alpha.1"
__author__ = "Justadudeinspace"
__email__ = "justadudeinspace@example.com"

from .core import (
    parse_schema,
    realize,
    get_default_output_dir,
    print_platform_info,
    do_bootstrap,
    ParseError,
)
from .audit import run_dat_audit
from .cli import main as cli_main

__all__ = [
    "parse_schema",
    "realize",
    "get_default_output_dir",
    "print_platform_info",
    "do_bootstrap",
    "ParseError",
    "run_dat_audit",
    "cli_main",
]
