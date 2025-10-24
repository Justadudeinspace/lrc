"""Template and code generation helpers for LRC."""

from __future__ import annotations

from typing import Dict, List
from pathlib import Path

from ..core import template_actions as _template_actions
from ..core import expand_vars as _expand_vars

__all__ = ["template_actions", "expand_vars"]


def template_actions(name: str, root: Path, vars_: Dict[str, str]) -> List["Action"]:
    return _template_actions(name, root, vars_)


def expand_vars(value: str, vars_: Dict[str, str]) -> str:
    return _expand_vars(value, vars_)
