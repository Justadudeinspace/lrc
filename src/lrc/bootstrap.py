"""Utility helpers for the ``--bootstrap`` flag."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .compiler import IS_WINDOWS


def detect_install_bin() -> Path:
    if _is_termux():
        return Path("/data/data/com.termux/files/usr/bin")
    if IS_WINDOWS:
        for candidate in [
            Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps",
            Path.home() / "AppData" / "Local" / "Programs" / "Python",
        ]:
            if candidate.exists():
                return candidate
        return Path.home() / "AppData" / "Local" / "bin"
    return Path.home() / ".local" / "bin"


def persist_path(bin_dir: Path, verbose: bool = False) -> None:
    export_line = f'export PATH="{bin_dir}:$PATH"'
    shell = os.environ.get("SHELL", "").split("/")[-1] or "bash"
    targets = {
        "zsh": [Path.home() / ".zshrc", Path.home() / ".zprofile"],
        "bash": [Path.home() / ".bashrc", Path.home() / ".bash_profile", Path.home() / ".profile"],
        "fish": [Path.home() / ".config" / "fish" / "config.fish"],
        "pwsh": [Path.home() / "Documents" / "PowerShell" / "profile.ps1"],
    }
    for rc in targets.get(shell, targets["bash"]):
        try:
            rc.parent.mkdir(parents=True, exist_ok=True)
            rc.touch(exist_ok=True)
            content = rc.read_text(encoding="utf-8")
            if export_line not in content:
                rc.write_text(content + f"\n# Added by lrc\n{export_line}\n", encoding="utf-8")
                if verbose:
                    print(f"[PATH] Updated {rc}")
        except OSError as exc:
            if verbose:
                print(f"[WARN] Could not update {rc}: {exc}")


def do_bootstrap(argv0: str, verbose: bool = False) -> Path:
    bin_dir = detect_install_bin()
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / ("lrc.exe" if IS_WINDOWS else "lrc")
    source = Path(argv0).resolve()
    if not source.exists():
        source = Path(__file__).resolve()
    shutil.copy2(source, target)
    if not IS_WINDOWS:
        target.chmod(0o755)
    persist_path(bin_dir, verbose)
    if verbose:
        print(f"[BOOTSTRAP] Installed to {target}")
    return target


def _is_termux() -> bool:
    return "com.termux" in os.environ.get("PREFIX", "")
