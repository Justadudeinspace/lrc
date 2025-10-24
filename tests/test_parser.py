from pathlib import Path

import pytest

from lrc.parser import ParseError, parse_schema


def test_parse_basic_schema(tmp_path: Path) -> None:
    schema = Path("tests/data/simple.lrc").read_text(encoding="utf-8")
    result = parse_schema(schema, tmp_path, Path("tests/data"))
    assert result.metadata["Project"] == "demo-app"
    assert result.variables["AUTHOR"] == "Unit Tester"
    paths = {action.path.relative_to(tmp_path) for action in result.actions if action.kind == "write"}
    assert Path("src/main.py") in paths


def test_template_expansion(tmp_path: Path) -> None:
    schema = """
# Project: template-demo
@template python-cli
"""
    result = parse_schema(schema, tmp_path, tmp_path)
    written = {action.path.relative_to(tmp_path) for action in result.actions if action.kind == "write"}
    assert Path("pyproject.toml") in written
    assert any("python" in action.content.lower() for action in result.actions if action.content)


def test_invalid_directive_raises(tmp_path: Path) -> None:
    schema = "@unknown value"
    with pytest.raises(ParseError):
        parse_schema(schema, tmp_path, tmp_path)
