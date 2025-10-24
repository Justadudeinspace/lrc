"""DAT integration helpers for the LRC CLI."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from .compiler import BuildPlan

CONFIG_PATH = Path.home() / ".config" / "lrc" / "dat_integration.json"
DEFAULT_CONFIG = {
    "version": "1",
    "dat_exec": "dat",
    "audit_defaults": {
        "ignore": [".git", "__pycache__", ".venv", "node_modules"],
        "max_lines": 1000,
        "max_size": 10485760,
    },
    "gpg": {"enable_signing": True, "signing_key": ""},
}


def ensure_dat_config(verbose: bool = False) -> Dict[str, object]:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    if verbose:
        print(f"[audit] created integration config at {CONFIG_PATH}")
    return DEFAULT_CONFIG.copy()


def run_dat_audit(
    plan: BuildPlan,
    output_dir: Path,
    *,
    audit_out: Optional[Path] = None,
    audit_format: str = "json",
    audit_args: str = "",
    verbose: bool = False,
) -> Dict[str, object]:
    config = ensure_dat_config(verbose=verbose)
    dat_exec = str(config.get("dat_exec", "dat"))
    audit_format = audit_format.lower()

    command = [dat_exec, "--from-lrc", str(output_dir)]

    if audit_args:
        command.extend(shlex.split(audit_args))

    started = time.time()
    mocked = False
    exit_code = 0
    stdout = ""
    stderr = ""

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        exit_code = result.returncode
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
    except FileNotFoundError:
        mocked = True
        exit_code = 127
        stderr = "dat executable not found; using mocked audit"
    except OSError as exc:
        mocked = True
        exit_code = 127
        stderr = f"failed to execute dat: {exc}"

    duration = time.time() - started
    summary: Dict[str, object] = {
        "command": command,
        "exit_code": exit_code,
        "duration": duration,
        "timestamp": int(started),
        "mocked": mocked,
        "stdout": stdout,
        "stderr": stderr,
        "defaults": config.get("audit_defaults", {}),
        "project": plan.project_name,
    }

    audit_path = output_dir / ".lrc-audit.json"
    audit_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    if audit_format in {"pdf", "combined"}:
        pdf_path = output_dir / "audit.pdf"
        pdf_path.write_text("DAT audit placeholder PDF", encoding="utf-8")
        if config.get("gpg", {}).get("enable_signing"):
            asc_path = output_dir / "audit.pdf.asc"
            asc_path.write_text("signed-placeholder", encoding="utf-8")
    if audit_format in {"md", "combined"}:
        md_path = output_dir / "audit.md"
        md_path.write_text("# DAT Audit\n\nThis is a placeholder report.", encoding="utf-8")

    if audit_out:
        audit_out.parent.mkdir(parents=True, exist_ok=True)
        if audit_format == "json":
            audit_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        elif audit_format == "pdf":
            audit_out.write_text("DAT audit placeholder PDF", encoding="utf-8")
        elif audit_format == "md":
            audit_out.write_text("# DAT Audit\n\nPlaceholder report.", encoding="utf-8")
        elif audit_format == "combined":
            base = audit_out
            audit_out_json = base.with_suffix(".json")
            audit_out_pdf = base.with_suffix(".pdf")
            audit_out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            audit_out_pdf.write_text("DAT audit placeholder PDF", encoding="utf-8")

    if verbose:
        status = "mocked" if mocked else "completed"
        print(f"[audit] {status} with exit code {exit_code}")

    return summary
