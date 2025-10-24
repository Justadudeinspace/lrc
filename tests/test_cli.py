import json
from pathlib import Path

from lrc.main import main


SCHEMA = Path("tests/data/simple.lrc")


def test_cli_dry_run(tmp_path):
    out_dir = tmp_path / "dry"
    code = main([str(SCHEMA), "--out", str(out_dir), "--dry-run"])
    assert code == 0
    assert not out_dir.exists()


def test_cli_generates_manifest(tmp_path):
    out_dir = tmp_path / "build"
    code = main([str(SCHEMA), "--out", str(out_dir)])
    assert code == 0
    manifest = out_dir / ".lrc-build.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text())
    assert data["project"] == "demo-app"
