from __future__ import annotations

import json
from pathlib import Path

import pytest

from lrc.core import (
    DEFAULT_TRUSTED_TEMPLATES,
    ParseError,
    load_trusted_templates,
    parse_schema,
)


def test_load_trusted_templates_uses_default(tmp_path: Path) -> None:
    policy = load_trusted_templates(tmp_path)
    assert DEFAULT_TRUSTED_TEMPLATES.issubset(policy)


def test_parse_schema_rejects_untrusted_template(tmp_path: Path) -> None:
    schema = """\n@template forbidden\n"""
    out_root = tmp_path / "out"
    with pytest.raises(ParseError):
        parse_schema(schema, out_root, tmp_path)


def test_parse_schema_allows_trusted_template(tmp_path: Path) -> None:
    policy_file = tmp_path / "trusted_templates.json"
    policy_file.write_text(json.dumps(["custom-template"]))

    schema = """\n@template custom-template\n"""
    out_root = tmp_path / "out"
    actions, meta, vars_ = parse_schema(schema, out_root, tmp_path)
    # Template expands into at least one action (README fallback)
    assert actions
    assert meta == {"Project": None, "Description": None, "Version": None}
    assert vars_["AUTHOR"] == ""
