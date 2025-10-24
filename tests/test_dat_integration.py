from __future__ import annotations

import json
from pathlib import Path

from lrc.audit import run_dat_audit


def test_run_dat_audit_success(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "enabled": True,
                "command": ["python", "-c", "print('audit-ok')"],
            }
        )
    )

    result = run_dat_audit(tmp_path, config_path=config, logger=lambda *_: None)

    assert result["status"] == "passed"
    assert "audit-ok" in result.get("stdout", "")


def test_run_dat_audit_skipped_when_config_missing(tmp_path: Path) -> None:
    result = run_dat_audit(
        tmp_path, config_path=tmp_path / "missing.json", logger=lambda *_: None
    )
    assert result["status"] == "skipped"
