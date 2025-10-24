"""Apply compiled actions to the filesystem."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .compiler import BuildPlan, build_metadata
from .parser import Action, is_safe_under_base

__all__ = ["GenerationResult", "realize", "write_build_manifest"]


@dataclass
class GenerationResult:
    success: bool
    created_paths: List[Path]


def realize(
    plan: BuildPlan,
    output_dir: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> GenerationResult:
    created: List[Path] = []
    success = True

    for action in plan.actions:
        path = action.path
        if not is_safe_under_base(path, output_dir):
            print(f"[SECURITY] Skipping unsafe path: {path}")
            success = False
            continue

        if action.kind == "mkdir":
            if verbose or dry_run:
                print(f"[{'DRY' if dry_run else 'mkdir'}] {path}")
            if dry_run:
                continue
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
            continue

        if action.kind == "write":
            if verbose or dry_run:
                size = len(action.content or "")
                print(f"[{'DRY' if dry_run else 'write'}] {path} ({size} bytes)")
            if dry_run:
                continue
            if path.exists() and not force:
                print(f"[WARN] Skipping existing file (use --force to overwrite): {path}")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.content or "", encoding="utf-8")
            created.append(path)
            continue

        if action.kind == "chmod":
            if verbose or dry_run:
                print(f"[{'DRY' if dry_run else 'chmod'}] {path} {oct(action.mode or 0o644)}")
            if dry_run:
                continue
            if os.name != "nt":
                try:
                    path.chmod(action.mode or 0o644)
                except FileNotFoundError:
                    pass
            continue

        if action.kind == "copy":
            if verbose or dry_run:
                print(f"[{'DRY' if dry_run else 'copy'}] {action.src} -> {path}")
            if dry_run:
                continue
            if path.exists() and not force:
                print(f"[WARN] Skipping existing file (use --force to overwrite): {path}")
                continue
            if not action.src or not action.src.exists():
                print(f"[ERROR] Copy source missing: {action.src}")
                success = False
                continue
            if not is_safe_under_base(action.src, action.src.parent):
                print(f"[SECURITY] Skipping unsafe copy source: {action.src}")
                success = False
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(action.src, path)
            created.append(path)
            continue

        if action.kind == "symlink":
            if verbose or dry_run:
                print(f"[{'DRY' if dry_run else 'symlink'}] {action.target} -> {path}")
            if dry_run:
                continue
            if path.exists():
                if force:
                    if path.is_symlink() or path.is_file():
                        path.unlink()
                else:
                    print(
                        f"[WARN] Skipping existing symlink (use --force to overwrite): {path}"
                    )
                    continue
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.symlink_to(action.target)
            except OSError as exc:
                print(f"[ERROR] Failed to create symlink {path}: {exc}")
                success = False
            else:
                created.append(path)
            continue

        print(f"[WARN] Unknown action kind: {action.kind}")

    return GenerationResult(success=success, created_paths=created)


def write_build_manifest(
    plan: BuildPlan,
    output_dir: Path,
    *,
    dry_run: bool,
    audit_summary: Optional[Dict[str, object]] = None,
) -> Optional[Path]:
    if dry_run:
        return None
    manifest_path = output_dir / ".lrc-build.json"
    manifest = build_metadata(plan)
    manifest.update(
        {
            "output": str(output_dir),
            "timestamp": int(time.time()),
        }
    )
    if audit_summary is not None:
        manifest["audit"] = audit_summary
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path
