"""Parser interfaces for LRC schemas."""

from __future__ import annotations

from typing import Dict, List, Tuple
from pathlib import Path

from ..core import ParseError, ParserState, parse_schema as _parse_schema

__all__ = ["ParseError", "ParserState", "parse_schema"]


def parse_schema(
    schema_text: str, out_root: Path, base_dir: Path, verbose: bool = False
) -> Tuple[List["Action"], Dict[str, str], Dict[str, str]]:
    """Typed wrapper that delegates to the legacy parser implementation.

    The parser package provides an extension point for the refactored
    architecture without breaking backward compatibility with the
    existing `lrc.core` module.  Consumers should import the parser
    through ``lrc.parser`` instead of ``lrc.core``.
    """

    return _parse_schema(schema_text, out_root, base_dir, verbose)
