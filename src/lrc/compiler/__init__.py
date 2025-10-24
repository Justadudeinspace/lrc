"""Compilation helpers for LRC actions."""

from __future__ import annotations

from typing import List
from pathlib import Path

from ..core import Action as _Action, realize as _realize

Action = _Action
__all__ = ["Action", "realize"]


def realize(
    actions: List[_Action],
    base_dir: Path,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> bool:
    """Execute actions using the legacy implementation."""

    return _realize(actions, base_dir, dry_run, force, verbose)
