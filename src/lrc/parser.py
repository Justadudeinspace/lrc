"""Schema parsing utilities for LRC.

This module converts declarative ``.lrc`` schema files into a sequence of
filesystem actions that later stages of the compiler can realise.  It handles
variable expansion, heredocs, nested includes, template expansion, ignore
patterns and security enforcement for paths and file types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Dict, Iterable, List, Literal, Optional, Tuple

try:
    from importlib import resources as importlib_resources
except ImportError:  # pragma: no cover - Python <3.9 fallback
    import importlib_resources  # type: ignore


__all__ = [
    "Action",
    "GPGReport",
    "ParseError",
    "ParserResult",
    "coalesce_mkdirs",
    "detect_signature_file",
    "expand_vars",
    "is_safe_under_base",
    "load_trusted_templates",
    "normalize_line_endings",
    "parse_schema",
    "validate_file_extension",
]


SYSTEM = os.uname().sysname.lower() if hasattr(os, "uname") else "windows"
IS_WINDOWS = SYSTEM.startswith("win")

DEFAULT_TRUSTED_TEMPLATES = {
    "python-cli",
    "node-cli",
    "rust-cli",
}

REQUIRE_SIGNED_IMPORTS = (
    os.environ.get("LRC_REQUIRE_SIGNED_INCLUDES", "").lower() in {"1", "true", "yes"}
)


@dataclass
class Action:
    """Filesystem action produced by the parser/ compiler."""

    kind: Literal["mkdir", "write", "chmod", "copy", "symlink"]
    path: Path
    content: Optional[str] = None
    mode: Optional[int] = None
    src: Optional[Path] = None
    target: Optional[Path] = None


@dataclass
class GPGReport:
    """Result of verifying a schema or include signature."""

    path: str
    verified: bool
    signature: Optional[str] = None
    message: Optional[str] = None


@dataclass
class ParserResult:
    """Container for the parser output."""

    actions: List[Action]
    metadata: Dict[str, Optional[str]]
    variables: Dict[str, str]
    ignores: List[str]
    gpg_reports: List[GPGReport] = field(default_factory=list)


@dataclass
class ParseError(Exception):
    """Exception raised for schema parsing issues."""

    line_num: int
    message: str
    line_content: str = ""

    def __str__(self) -> str:  # pragma: no cover - convenience
        if self.line_content:
            return f"Line {self.line_num}: {self.message}\n  {self.line_content}"
        return f"Line {self.line_num}: {self.message}"


class ParserState:
    """Internal mutable state used while parsing a schema."""

    def __init__(self, out_root: Path):
        self.out_root = out_root
        self.dir_stack: List[Path] = [out_root]
        self.indent_stack: List[int] = [0]
        self.actions: List[Action] = []
        self.meta: Dict[str, Optional[str]] = {
            "Project": None,
            "Description": None,
            "Version": None,
        }
        self.vars: Dict[str, str] = {
            "AUTHOR": "",
            "PROJECT": "",
            "DESCRIPTION": "",
            "VERSION": "",
            "PKG": "",
        }
        self.ignores: List[str] = []
        self.heredoc_stack: List[Tuple[str, Path, int]] = []  # (marker, path, start_index)
        self.trusted_templates: Optional[set[str]] = None
        self.base_dir: Path = out_root
        self.gpg_reports: List[GPGReport] = []

    def current_dir(self) -> Path:
        return self.dir_stack[-1]


# ---------------------------------------------------------------------------
# Utility helpers


def get_safe_path(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):  # pragma: no cover - fallback path handling
        return path.absolute()


def normalize_line_endings(content: str, target: Optional[str] = None) -> str:
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if target is None:
        target = "windows" if IS_WINDOWS else "unix"
    if target == "windows":
        content = content.replace("\n", "\r\n")
    return content


def expand_vars(value: str, vars_: Dict[str, str]) -> str:
    if not value:
        return value

    pattern = re.compile(r"\$\{([^}]+)\}")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return vars_.get(key, match.group(0))

    return pattern.sub(repl, value)


def validate_file_extension(filename: str) -> bool:
    dangerous = {
        ".exe",
        ".bat",
        ".cmd",
        ".sh",
        ".bin",
        ".app",
        ".dmg",
        ".pkg",
        ".deb",
        ".rpm",
        ".msi",
    }
    ext = Path(filename).suffix.lower()
    return ext not in dangerous


def is_safe_under_base(path: Path, base_dir: Path) -> bool:
    try:
        base_real = os.path.realpath(str(get_safe_path(base_dir)))
        target_real = os.path.realpath(str(get_safe_path(path)))
        return os.path.commonpath([base_real, target_real]) == base_real
    except (ValueError, OSError):
        return False


def load_trusted_templates(base_dir: Path) -> set[str]:
    candidates = [
        base_dir / "trusted_templates.json",
        base_dir / ".lrc" / "trusted_templates.json",
        Path.home() / ".config" / "lrc" / "trusted_templates.json",
        Path(__file__).resolve().parent.parent / "trusted_templates.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ParseError(0, f"Invalid trusted template policy: {candidate}", str(exc))
            if isinstance(data, list):
                return {str(item).strip() for item in data if str(item).strip()}
    return set(DEFAULT_TRUSTED_TEMPLATES)


# ---------------------------------------------------------------------------
# Signature validation helpers


def detect_signature_file(schema_path: Path) -> Optional[Path]:
    candidates = [
        schema_path.with_name(schema_path.name + ".asc"),
        schema_path.with_name(schema_path.name + ".sig"),
        schema_path.with_suffix(schema_path.suffix + ".asc"),
        schema_path.with_suffix(schema_path.suffix + ".sig"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def verify_include_signature(
    include_path: Path,
    st: ParserState,
    line_num: int,
    line: str,
    verbose: bool,
) -> None:
    signature = detect_signature_file(include_path)
    if not signature:
        if REQUIRE_SIGNED_IMPORTS:
            raise ParseError(line_num, f"No signature found for include: {include_path.name}", line)
        st.gpg_reports.append(
            GPGReport(path=str(include_path), verified=False, message="signature missing")
        )
        return

    if shutil.which("gpg") is None:
        raise ParseError(line_num, "GPG executable not available for signature verification", line)

    result = subprocess.run(
        ["gpg", "--verify", str(signature), str(include_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ParseError(
            line_num,
            f"GPG signature verification failed for {include_path.name}",
            stderr or line,
        )
    st.gpg_reports.append(
        GPGReport(path=str(include_path), verified=True, signature=str(signature))
    )
    if verbose:
        print(f"[tag] verified signature {signature}")


# ---------------------------------------------------------------------------
# Template loading


def _iter_template_entries(name: str) -> Iterable[Tuple[str, Optional[str]]]:
    base = importlib_resources.files("lrc.templates").joinpath(name)
    if not base.is_dir():
        raise FileNotFoundError(name)

    stack = [(base, Path(""))]
    while stack:
        current, rel = stack.pop()
        for entry in current.iterdir():
            relative = rel / entry.name
            if entry.is_dir():
                yield str(relative) + "/", None
                stack.append((entry, relative))
            else:
                try:
                    text = entry.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    text = ""
                yield str(relative), text


def template_actions(name: str, st: ParserState, verbose: bool) -> List[Action]:
    acts: List[Action] = []
    normalized = name.lower().strip()
    if st.trusted_templates is not None and normalized not in st.trusted_templates:
        raise ParseError(0, f"Template '{name}' is not trusted", name)

    try:
        for rel_path, content in _iter_template_entries(normalized):
            rel_path = expand_vars(rel_path, st.vars)
            target = st.out_root / rel_path.strip("/")
            if rel_path.endswith("/"):
                acts.append(Action("mkdir", target))
            else:
                acts.append(Action("write", target, normalize_line_endings(content or "")))
                if not IS_WINDOWS and target.suffix in (".sh", ".py"):
                    acts.append(Action("chmod", target, mode=0o755))
        if verbose:
            print(f"[tag] @template {name} ({len(acts)} actions)")
    except FileNotFoundError:
        raise ParseError(0, f"Template '{name}' not found", name)
    return acts


# ---------------------------------------------------------------------------
# Parsing implementation


def parse_schema(
    schema_text: str,
    out_root: Path,
    base_dir: Path,
    *,
    verbose: bool = False,
) -> ParserResult:
    st = ParserState(out_root)
    st.base_dir = base_dir
    st.trusted_templates = load_trusted_templates(base_dir)
    lines = schema_text.splitlines()

    _extract_metadata_and_vars(lines, st, verbose)

    index = 0
    while index < len(lines):
        try:
            index = _parse_line(lines, index, st, base_dir, verbose)
        except ParseError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise ParseError(
                index + 1,
                f"Unexpected error: {exc}",
                lines[index] if index < len(lines) else "",
            )

    if st.ignores:
        st.actions = _filter_ignored_actions(st.actions, st.ignores, verbose)

    return ParserResult(
        actions=coalesce_mkdirs(st.actions),
        metadata=st.meta,
        variables=st.vars,
        ignores=st.ignores,
        gpg_reports=st.gpg_reports,
    )


def _extract_metadata_and_vars(lines: List[str], st: ParserState, verbose: bool) -> None:
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue

        stripped = line.strip()
        if stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            for key in ("Project", "Description", "Version"):
                prefix = f"{key}:"
                if body.lower().startswith(prefix.lower()):
                    value = body[len(prefix) :].strip()
                    if value:
                        st.meta[key] = value
                        st.vars[key.upper()] = value
                        if key == "Project" and not st.vars.get("PKG"):
                            st.vars["PKG"] = re.sub(r"[^a-zA-Z0-9]+", "-", value).lower()
            continue

        if stripped.startswith("@set "):
            body = stripped[len("@set ") :].strip()
            if "=" not in body:
                continue
            key, value = body.split("=", 1)
            key = key.strip()
            value = value.strip()
            st.vars[key] = value
            if verbose:
                print(f"[parse] @set {key} = {value}")


def _parse_line(
    lines: List[str],
    index: int,
    st: ParserState,
    base_dir: Path,
    verbose: bool,
) -> int:
    raw = lines[index]
    line_num = index + 1

    if not raw.strip() or raw.lstrip().startswith("#"):
        return index + 1

    stripped = raw.strip()
    if stripped.startswith("@"):
        return _handle_directive(stripped, st, base_dir, line_num, verbose, index, lines)

    if st.heredoc_stack:
        return _handle_heredoc_continuation(raw, lines, index, st, line_num, verbose)

    leading_spaces = len(raw) - len(raw.lstrip())
    _adjust_directory_stack(leading_spaces, st)

    entry = raw.strip()
    if entry.startswith("/"):
        return _handle_absolute_section(entry, st, line_num, verbose)
    if entry.endswith("/") and "->" not in entry and "<<" not in entry:
        return _handle_directory(entry, leading_spaces, st, line_num, verbose)
    if "<<" in entry:
        return _handle_heredoc_start(entry, lines, index, st, line_num, verbose)
    if "->" in entry:
        return _handle_inline_file(entry, st, line_num, verbose)
    return _handle_plain_file(entry, st, line_num, verbose)


def _adjust_directory_stack(leading_spaces: int, st: ParserState) -> None:
    while st.indent_stack and leading_spaces < st.indent_stack[-1]:
        st.indent_stack.pop()
        st.dir_stack.pop()

    if leading_spaces > st.indent_stack[-1]:
        st.indent_stack.append(leading_spaces)


def _handle_absolute_section(entry: str, st: ParserState, line_num: int, verbose: bool) -> int:
    section = entry.lstrip("/")
    if section.endswith("/"):
        section = section[:-1]
    section = expand_vars(section, st.vars)
    new_dir = st.out_root / Path(section)
    st.actions.append(Action("mkdir", new_dir))
    if st.indent_stack[-1] == (len(entry) - len(entry.lstrip())):
        st.dir_stack[-1] = new_dir
    else:
        st.dir_stack.append(new_dir)
    if verbose:
        print(f"[parse] L{line_num}: enter /{section}")
    return line_num


def _handle_directory(
    entry: str,
    leading_spaces: int,
    st: ParserState,
    line_num: int,
    verbose: bool,
) -> int:
    dir_name = expand_vars(entry[:-1].strip(), st.vars)
    new_dir = st.current_dir() / dir_name
    st.actions.append(Action("mkdir", new_dir))
    if st.indent_stack and (leading_spaces > st.indent_stack[-1]):
        st.dir_stack.append(new_dir)
    else:
        st.dir_stack[-1] = new_dir
    if verbose:
        print(f"[parse] L{line_num}: dir {new_dir}")
    return line_num


def _handle_heredoc_start(
    entry: str,
    lines: List[str],
    index: int,
    st: ParserState,
    line_num: int,
    verbose: bool,
) -> int:
    left, marker = entry.split("<<", 1)
    file_name = expand_vars(left.strip(), st.vars)
    marker = marker.strip() or "EOF"
    target_path = st.current_dir() / file_name
    if not validate_file_extension(file_name):
        raise ParseError(line_num, f"Potentially dangerous file extension: {file_name}", entry)
    st.heredoc_stack.append((marker, target_path, index + 1))
    if verbose:
        print(f"[parse] L{line_num}: heredoc start {file_name} <<{marker}")
    return index + 1


def _handle_heredoc_continuation(
    raw: str,
    lines: List[str],
    index: int,
    st: ParserState,
    line_num: int,
    verbose: bool,
) -> int:
    marker, target_path, start_line = st.heredoc_stack[-1]
    if raw.strip() == marker:
        content_lines = lines[start_line:index]
        content = "\n".join(content_lines)
        content = expand_vars(content, st.vars)
        content = normalize_line_endings(content)
        st.actions.append(Action("write", target_path, content))
        if not IS_WINDOWS and target_path.suffix in (".sh", ".py", ".pl", ".rb"):
            st.actions.append(Action("chmod", target_path, mode=0o755))
        if verbose:
            print(
                f"[parse] L{start_line}-{line_num - 1}: heredoc {target_path} ({len(content)} bytes)"
            )
        st.heredoc_stack.pop()
        return index + 1
    return index + 1


def _handle_inline_file(entry: str, st: ParserState, line_num: int, verbose: bool) -> int:
    left, right = entry.split("->", 1)
    file_name = expand_vars(left.strip(), st.vars)
    if not validate_file_extension(file_name):
        raise ParseError(line_num, f"Potentially dangerous file extension: {file_name}", entry)
    content = expand_vars(right.lstrip(), st.vars)
    content = normalize_line_endings(content)
    target_path = st.current_dir() / file_name
    st.actions.append(Action("write", target_path, content))
    if not IS_WINDOWS and target_path.suffix in (".sh", ".py", ".pl", ".rb"):
        st.actions.append(Action("chmod", target_path, mode=0o755))
    if verbose:
        print(f"[parse] L{line_num}: file {target_path} (inline, {len(content)} chars)")
    return line_num + 1


def _handle_plain_file(entry: str, st: ParserState, line_num: int, verbose: bool) -> int:
    file_name = expand_vars(entry, st.vars)
    if not validate_file_extension(file_name):
        raise ParseError(line_num, f"Potentially dangerous file extension: {file_name}", entry)
    target_path = st.current_dir() / file_name
    st.actions.append(Action("mkdir", target_path.parent))
    st.actions.append(Action("write", target_path, ""))
    if not IS_WINDOWS and target_path.suffix in (".sh", ".py", ".pl", ".rb"):
        st.actions.append(Action("chmod", target_path, mode=0o755))
    if verbose:
        print(f"[parse] L{line_num}: file {target_path} (empty)")
    return line_num + 1


def _handle_directive(
    line: str,
    st: ParserState,
    base_dir: Path,
    line_num: int,
    verbose: bool,
    index: int,
    lines: List[str],
) -> int:
    if line.startswith("@set "):
        body = line[len("@set ") :].strip()
        if "=" not in body:
            raise ParseError(line_num, "Invalid @set syntax, use: @set KEY=VALUE", line)
        key, value = body.split("=", 1)
        st.vars[key.strip()] = value.strip()
        if verbose:
            print(f"[tag] @set {key.strip()} = {value.strip()}")
        return index + 1

    if line.startswith("@include "):
        inc_file = expand_vars(line[len("@include ") :].strip(), st.vars)
        inc_path = (base_dir / inc_file).resolve()
        if not is_safe_under_base(inc_path, base_dir):
            raise ParseError(line_num, f"Included file path traversal detected: {inc_file}", line)
        if not inc_path.exists():
            raise ParseError(line_num, f"Included file not found: {inc_file}", line)
        verify_include_signature(inc_path, st, line_num, line, verbose)
        included_text = inc_path.read_text(encoding="utf-8")
        result = parse_schema(included_text, st.out_root, inc_path.parent, verbose=verbose)
        st.actions.extend(result.actions)
        st.vars.update(result.variables)
        st.gpg_reports.extend(result.gpg_reports)
        return index + 1

    if line.startswith("@ignore"):
        patterns = line.split()[1:]
        st.ignores.extend(patterns)
        if verbose:
            print(f"[tag] @ignore {patterns}")
        return index + 1

    if line.startswith("@chmod "):
        rest = line[len("@chmod ") :].strip()
        parts = rest.split()
        if len(parts) < 2:
            raise ParseError(line_num, "Invalid @chmod syntax, use: @chmod PATH MODE", line)
        path_str, mode_str = parts[0], parts[1]
        target_path = st.out_root / expand_vars(path_str, st.vars)
        mode = _parse_chmod_mode(mode_str)
        st.actions.append(Action("chmod", target_path, mode=mode))
        if verbose:
            print(f"[tag] @chmod {target_path} {oct(mode)}")
        return index + 1

    if line.startswith("@copy "):
        rest = line[len("@copy ") :].strip()
        parts = rest.split()
        if len(parts) < 2:
            raise ParseError(line_num, "Invalid @copy syntax, use: @copy SRC DEST", line)
        src_str, dest_str = parts[0], parts[1]
        src_path = (base_dir / expand_vars(src_str, st.vars)).resolve()
        dest_path = (st.out_root / expand_vars(dest_str, st.vars)).resolve()
        if not is_safe_under_base(src_path, base_dir):
            raise ParseError(line_num, f"Copy source path traversal detected: {src_str}", line)
        if not is_safe_under_base(dest_path, st.out_root):
            raise ParseError(line_num, f"Copy destination path traversal detected: {dest_str}", line)
        if not src_path.exists():
            raise ParseError(line_num, f"Copy source not found: {src_path}", line)
        st.actions.append(Action("copy", dest_path, src=src_path))
        if verbose:
            print(f"[tag] @copy {src_path} -> {dest_path}")
        return index + 1

    if line.startswith("@template "):
        template_name = line[len("@template ") :].strip()
        acts = template_actions(template_name, st, verbose)
        st.actions.extend(acts)
        return index + 1

    if line.startswith("@symlink "):
        rest = line[len("@symlink ") :].strip()
        parts = rest.split()
        if len(parts) < 2:
            raise ParseError(
                line_num,
                "Invalid @symlink syntax, use: @symlink TARGET LINKNAME",
                line,
            )
        target_str, link_str = parts[0], parts[1]
        target_path = Path(expand_vars(target_str, st.vars))
        link_path = st.out_root / expand_vars(link_str, st.vars)
        st.actions.append(Action("symlink", link_path, target=target_path))
        if verbose:
            print(f"[tag] @symlink {target_path} -> {link_path}")
        return index + 1

    raise ParseError(line_num, f"Unknown directive: {line.split()[0]}", line)


def _parse_chmod_mode(mode_str: str) -> int:
    if mode_str.startswith("+"):
        if "x" in mode_str:
            return 0o755
        if "w" in mode_str:
            return 0o644
        return 0o644
    try:
        if mode_str.startswith("0o"):
            return int(mode_str, 8)
        return int(mode_str, 8)
    except ValueError:
        return 0o644


def _filter_ignored_actions(actions: List[Action], ignores: List[str], verbose: bool) -> List[Action]:
    filtered: List[Action] = []
    for act in actions:
        rel_path = str(act.path)
        skip = False
        for pattern in ignores:
            if pattern in rel_path or fnmatch.fnmatch(rel_path, pattern):
                skip = True
                if verbose:
                    print(f"[filter] ignore {act.path} (pattern: {pattern})")
                break
        if not skip:
            filtered.append(act)
    return filtered


def coalesce_mkdirs(actions: List[Action]) -> List[Action]:
    seen_dirs = set()
    result: List[Action] = []
    for act in actions:
        if act.kind == "mkdir":
            if act.path not in seen_dirs:
                seen_dirs.add(act.path)
                result.append(act)
        else:
            result.append(act)
    return result
