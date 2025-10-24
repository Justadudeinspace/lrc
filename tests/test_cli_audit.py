from __future__ import annotations

from pathlib import Path

from lrc.cli import main as cli_main


def test_cli_runs_audit_skip(tmp_path: Path, capsys) -> None:
    schema = tmp_path / "schema.lrc"
    schema.write_text("""\n# Project: Audit Test\n@set AUTHOR=QA\nREADME.md\n""")
    output_dir = tmp_path / "output"

    exit_code = cli_main(
        [
            str(schema),
            "--output",
            str(output_dir),
            "--audit",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert output_dir.exists()
    assert "[AUDIT]" in captured.out
