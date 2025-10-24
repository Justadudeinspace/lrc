"""Compilation helpers for LRC.

The compiler module coordinates schema parsing, signature verification and
high-level planning before the generator materialises files on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .parser import (
    Action,
    GPGReport,
    ParseError,
    coalesce_mkdirs,
    detect_signature_file,
    parse_schema,
)

__all__ = [
    "BuildPlan",
    "ParseError",
    "compile_schema_path",
    "get_default_output_dir",
    "print_platform_info",
    "resolve_output_directory",
    "SYSTEM",
]

SYSTEM = platform.system().lower()
IS_WINDOWS = SYSTEM == "windows"
IS_LINUX = SYSTEM == "linux"
IS_MACOS = SYSTEM == "darwin"


@dataclass
class BuildPlan:
    """Structured representation of the actions required for a build."""

    source: Path
    root: Path
    actions: List[Action]
    metadata: Dict[str, str]
    variables: Dict[str, str]
    ignores: List[str]
    gpg_reports: List[GPGReport]
    schema_signature: Optional[GPGReport]

    @property
    def project_name(self) -> str:
        for key in ("Project", "PROJECT", "NAME"):
            value = self.metadata.get(key) or self.variables.get(key, "")
            if value:
                return value
        return self.source.stem

    def rebase(self, new_root: Path) -> "BuildPlan":
        if new_root == self.root:
            return self
        rebased_actions: List[Action] = []
        for action in self.actions:
            try:
                relative = action.path.relative_to(self.root)
                new_path = new_root / relative
            except ValueError:
                new_path = action.path
            rebased_actions.append(
                Action(
                    kind=action.kind,
                    path=new_path,
                    content=action.content,
                    mode=action.mode,
                    src=action.src,
                    target=action.target,
                )
            )
        return BuildPlan(
            source=self.source,
            root=new_root,
            actions=rebased_actions,
            metadata=self.metadata,
            variables=self.variables,
            ignores=self.ignores,
            gpg_reports=self.gpg_reports,
            schema_signature=self.schema_signature,
        )


def compile_schema_path(
    schema_path: Path,
    out_dir: Path,
    *,
    verbose: bool = False,
) -> BuildPlan:
    schema_path = schema_path.resolve()
    out_dir = out_dir.resolve()
    if not schema_path.exists():
        raise FileNotFoundError(schema_path)

    schema_signature = verify_schema_signature(schema_path, verbose=verbose)

    text = schema_path.read_text(encoding="utf-8")
    result = parse_schema(text, out_dir, schema_path.parent, verbose=verbose)

    metadata = {k: (v or "") for k, v in result.metadata.items()}

    return BuildPlan(
        source=schema_path,
        root=out_dir,
        actions=coalesce_mkdirs(result.actions),
        metadata=metadata,
        variables=result.variables,
        ignores=result.ignores,
        gpg_reports=result.gpg_reports,
        schema_signature=schema_signature,
    )


def verify_schema_signature(schema_path: Path, *, verbose: bool = False) -> Optional[GPGReport]:
    signature = detect_signature_file(schema_path)
    if not signature:
        return None
    if shutil.which("gpg") is None:
        raise ParseError(0, "GPG executable not available for schema verification", schema_path.name)
    result = subprocess.run(
        ["gpg", "--verify", str(signature), str(schema_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ParseError(0, f"Schema signature verification failed: {schema_path.name}", stderr)
    if verbose:
        print(f"[tag] verified schema signature {signature}")
    return GPGReport(path=str(schema_path), verified=True, signature=str(signature))


def sanitize_name(value: str) -> str:
    return re.sub(r"[^\w\-_.]", "_", value)


def get_default_output_dir(project_name: Optional[str] = None) -> Path:
    base_dir = Path.cwd()
    if IS_LINUX and _is_termux():
        base_dir = Path.home() / "projects"
        base_dir.mkdir(exist_ok=True)
    if project_name:
        return base_dir / sanitize_name(project_name)
    return base_dir / "lrc_output"


def resolve_output_directory(plan: BuildPlan, explicit: Optional[Path]) -> Path:
    if explicit:
        return explicit.resolve()
    project = plan.project_name
    return get_default_output_dir(project)


def check_fs_ok(path: Path) -> tuple[bool, str]:
    try:
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        test_file = parent / ".lrc_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        if IS_WINDOWS and len(str(path)) > 260:
            return False, "Path exceeds Windows MAX_PATH limit (260 chars)"
        return True, "OK"
    except PermissionError:
        return False, "Permission denied"
    except OSError as exc:
        return False, f"Filesystem error: {exc}"


def print_platform_info(verbose: bool = False) -> None:
    info = [
        f"Platform: {platform.platform()}",
        f"System: {SYSTEM}",
        f"Windows: {IS_WINDOWS}",
        f"Linux: {IS_LINUX}",
        f"macOS: {IS_MACOS}",
        f"Python: {platform.python_version()}",
    ]
    if verbose:
        info.extend(
            [
                f"Current dir: {Path.cwd()}",
                f"Home dir: {Path.home()}",
                f"Executable: {os.environ.get('PYTHONEXECUTABLE', '')}",
            ]
        )
    for line in info:
        print(f"[INFO] {line}")


def build_metadata(plan: BuildPlan) -> Dict[str, object]:
    data: Dict[str, object] = {
        "schema": str(plan.source),
        "root": str(plan.root),
        "project": plan.project_name,
        "metadata": plan.metadata,
        "variables": plan.variables,
        "ignores": plan.ignores,
        "gpg": [report.__dict__ for report in plan.gpg_reports],
    }
    if plan.schema_signature:
        data.setdefault("gpg", []).append(plan.schema_signature.__dict__)
    return data


def _is_termux() -> bool:
    return "com.termux" in os.environ.get("PREFIX", "")


import re
import shutil
import subprocess

