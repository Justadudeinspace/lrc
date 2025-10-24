import json
from pathlib import Path

from lrc.compiler import compile_schema_path
from lrc.generator import realize
from lrc.integration import run_dat_audit


def test_run_dat_audit_creates_summary(tmp_path):
    schema = Path("tests/data/simple.lrc")
    plan = compile_schema_path(schema, tmp_path / "out")
    out_dir = plan.root
    realize(plan, out_dir, dry_run=False, force=True)
    summary = run_dat_audit(plan, out_dir, audit_format="json")
    audit_file = out_dir / ".lrc-audit.json"
    assert audit_file.exists()
    data = json.loads(audit_file.read_text())
    assert data["mocked"] is True
    assert summary["project"] == "demo-app"
