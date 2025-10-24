"""
LRC - Local Repo Compile
Build local repositories from declarative text schemas.
"""

__version__ = "0.2.1"
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

__all__ = [
    "parse_schema",
    "realize", 
    "get_default_output_dir",
    "print_platform_info",
    "do_bootstrap",
    "ParseError",
]
