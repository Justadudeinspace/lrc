#!/usr/bin/env python3
"""
LRC — Local Repo Compiler
Build local repositories from declarative text schemas.

Cross-platform support for: Android/Termux, Android/Linux, Linux, WSL2, macOS, Windows
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import os
import platform
import shutil
import textwrap
import re
import fnmatch
import json
import subprocess
from typing import List, Optional, Tuple, Literal, Dict, Any, Set
import hashlib
import tempfile

# ----------------------------- Constants & Configuration --------------------

__version__ = "1.0.0-alpha.1"

SYSTEM = platform.system().lower()
IS_WINDOWS = SYSTEM == "windows"
IS_LINUX = SYSTEM == "linux"
IS_MACOS = SYSTEM == "darwin"
IS_ANDROID = (
    "android" in platform.platform().lower()
    or "linux-android" in platform.platform().lower()
)
IS_TERMUX = IS_ANDROID and "com.termux" in os.environ.get("PREFIX", "")
IS_WSL = False
if IS_LINUX:
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                IS_WSL = True
    except Exception:
        pass

LINE_ENDINGS = "windows" if IS_WINDOWS else "unix"

DEFAULT_TRUSTED_TEMPLATES: Set[str] = {
    "python-cli",
    "node-cli",
    "rust-cli",
}

REQUIRE_SIGNED_IMPORTS = os.environ.get("LRC_REQUIRE_SIGNED_INCLUDES", "").lower() in {
    "1",
    "true",
    "yes",
}

# ----------------------------- Data Models ---------------------------------

@dataclass
class Action:
    """Represents a filesystem operation to be performed."""
    kind: Literal["mkdir", "write", "chmod", "copy", "symlink"]
    path: Path
    content: Optional[str] = None
    mode: Optional[int] = None
    src: Optional[Path] = None
    target: Optional[Path] = None

    def __str__(self) -> str:
        base = f"{self.kind}: {self.path}"
        if self.kind == "write":
            return f"{base} ({len(self.content or '')} bytes)"
        elif self.kind == "chmod":
            return f"{base} (mode: {oct(self.mode or 0o644)})"
        elif self.kind == "copy":
            return f"{base} <- {self.src}"
        elif self.kind == "symlink":
            return f"{base} -> {self.target}"
        return base


@dataclass
class ParseError(Exception):
    """Custom exception for schema parsing errors."""
    line_num: int
    message: str
    line_content: str = ""

    def __str__(self) -> str:
        return f"Line {self.line_num}: {self.message}\n  {self.line_content}"


@dataclass
class GenerationResult:
    """Result of repository generation operation."""
    success: bool
    actions_performed: int
    errors: List[str]
    warnings: List[str]

    def __bool__(self) -> bool:
        return self.success


# ----------------------------- Trust & Verification ------------------------

def load_trusted_templates(base_dir: Path) -> Set[str]:
    """
    Load template trust policy from disk.
    
    Args:
        base_dir: Base directory to search for trust configuration
        
    Returns:
        Set of trusted template names
    """
    candidates = [
        base_dir / "trusted_templates.json",
        base_dir / ".lrc" / "trusted_templates.json",
        Path.home() / ".config" / "lrc" / "trusted_templates.json",
        Path(__file__).resolve().parent.parent / "trusted_templates.json",
        Path(__file__).resolve().parents[2] / "trusted_templates.json",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return {str(item).strip() for item in data if str(item).strip()}
                elif isinstance(data, dict) and "templates" in data:
                    return {str(item).strip() for item in data["templates"] if str(item).strip()}
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ParseError(
                    0, f"Invalid trusted template policy: {candidate}", str(exc)
                ) from exc
            except Exception as exc:
                # Continue to next candidate on other errors
                continue
    
    return DEFAULT_TRUSTED_TEMPLATES


def _detect_signature_file(include_path: Path) -> Optional[Path]:
    """
    Detect signature file for an included schema.
    
    Args:
        include_path: Path to the included schema file
        
    Returns:
        Path to signature file if found, None otherwise
    """
    candidates = [
        include_path.with_name(include_path.name + ".asc"),
        include_path.with_name(include_path.name + ".sig"),
        include_path.with_suffix(include_path.suffix + ".asc"),
        include_path.with_suffix(include_path.suffix + ".sig"),
        include_path.parent / (include_path.name + ".asc"),
        include_path.parent / (include_path.name + ".sig"),
    ]
    
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        if cand.exists() and cand.is_file():
            return cand
    return None


def verify_include_signature(
    include_path: Path, line_num: int, line: str, verbose: bool
) -> None:
    """
    Ensure that included schema files are signed by a trusted key.
    
    Args:
        include_path: Path to included schema file
        line_num: Line number in original schema
        line: Original line content
        verbose: Enable verbose output
        
    Raises:
        ParseError: If signature verification fails
    """
    signature = _detect_signature_file(include_path)
    if not signature:
        if REQUIRE_SIGNED_IMPORTS:
            raise ParseError(
                line_num, f"No signature found for include: {include_path.name}", line
            )
        return
    
    if shutil.which("gpg") is None:
        raise ParseError(
            line_num, "GPG executable not available for signature verification", line
        )
    
    try:
        result = subprocess.run(
            ["gpg", "--verify", str(signature), str(include_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,  # Prevent hanging on large files
        )
        
        if result.returncode != 0:
            stderr = result.stderr.strip()
            error_msg = stderr.split('\n')[0] if stderr else "Unknown GPG error"
            raise ParseError(
                line_num,
                f"GPG signature verification failed for {include_path.name}: {error_msg}",
                line,
            )
            
        if verbose:
            print(f"[VERIFY] ✓ Verified signature {signature.name}")
            
    except subprocess.TimeoutExpired:
        raise ParseError(
            line_num, "GPG signature verification timed out", line
        )
    except Exception as exc:
        raise ParseError(
            line_num, f"GPG verification error: {exc}", line
        )


# ----------------------------- Security & Utilities ------------------------

def get_safe_path(path: Path) -> Path:
    """
    Get safe, normalized path with proper error handling.
    
    Args:
        path: Input path to normalize
        
    Returns:
        Normalized absolute path
    """
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError):
        return path.absolute()


def normalize_line_endings(content: str, target: str = LINE_ENDINGS) -> str:
    """
    Normalize line endings for target platform.
    
    Args:
        content: Text content to normalize
        target: Target line ending style ('windows' or 'unix')
        
    Returns:
        Content with normalized line endings
    """
    if not content:
        return content
        
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if target == "windows":
        content = content.replace("\n", "\r\n")
    return content


def expand_vars(s: str, vars_: Dict[str, str]) -> str:
    """
    Expand ${VAR} variables with proper escaping and error handling.
    
    Args:
        s: String containing variables to expand
        vars_: Dictionary of variable names to values
        
    Returns:
        String with variables expanded
    """
    if not s:
        return s

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in vars_:
            return vars_[var_name]
        # Leave unknown variables as-is for later resolution
        return match.group(0)

    pattern = r"\$\{([^}]+)\}"
    return re.sub(pattern, replace_var, s)


def is_safe_under_base(path: Path, base_dir: Path) -> bool:
    """
    Enhanced security check to prevent path traversal.
    
    Args:
        path: Target path to check
        base_dir: Base directory that path must be contained within
        
    Returns:
        True if path is safe, False otherwise
    """
    try:
        base_real = os.path.realpath(str(get_safe_path(base_dir)))
        target_real = os.path.realpath(str(get_safe_path(path)))
        common = os.path.commonpath([base_real, target_real])
        return common == base_real
    except (ValueError, OSError, RuntimeError):
        return False


def validate_file_extension(filename: str) -> bool:
    """
    Validate file extensions for security.
    
    Args:
        filename: Name of file to validate
        
    Returns:
        True if extension is safe, False otherwise
    """
    dangerous_extensions = {
        ".exe", ".bat", ".cmd", ".sh", ".bin", ".app", ".dmg", 
        ".pkg", ".deb", ".rpm", ".msi", ".scr", ".com", ".vbs",
        ".ps1", ".psm1", ".jar", ".war", ".apk", ".ipa",
    }

    ext = Path(filename).suffix.lower()
    return ext not in dangerous_extensions


def get_default_output_dir(project_name: Optional[str] = None) -> Path:
    """
    Get platform-appropriate default output directory.
    
    Args:
        project_name: Optional project name to use in directory path
        
    Returns:
        Path to default output directory
    """
    base_dir = Path.cwd()

    if IS_TERMUX:
        base_dir = Path.home() / "projects"
        base_dir.mkdir(exist_ok=True)
    elif IS_ANDROID:
        for candidate in ["Downloads", "Documents", "projects"]:
            candidate_path = Path.home() / candidate
            if candidate_path.exists() and os.access(candidate_path, os.W_OK):
                base_dir = candidate_path
                break
        else:
            # Create projects directory if no suitable one exists
            base_dir = Path.home() / "projects"
            base_dir.mkdir(exist_ok=True)

    if project_name:
        # Sanitize project name for filesystem safety
        safe_name = re.sub(r"[^\w\-_.]", "_", project_name)
        return base_dir / safe_name
    else:
        return base_dir / "lrc_output"


def check_fs_ok(path: Path) -> Tuple[bool, str]:
    """
    Check filesystem compatibility and permissions.
    
    Args:
        path: Path to check
        
    Returns:
        Tuple of (is_ok, message)
    """
    try:
        # Check parent directory writability
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)

        # Test write permissions
        test_file = parent / ".lrc_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink(missing_ok=True)

        # Platform-specific checks
        if IS_WINDOWS:
            # Windows path length limit
            if len(str(path)) > 260:
                return False, "Path exceeds Windows MAX_PATH limit (260 chars)"
            
            # Check for reserved names
            reserved_names = {
                "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3",
                "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
            }
            if path.stem.upper() in reserved_names:
                return False, f"Reserved Windows name: {path.stem}"

        return True, "OK"
        
    except PermissionError:
        return False, "Permission denied"
    except OSError as e:
        return False, f"Filesystem error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def print_platform_info(verbose: bool = False) -> None:
    """Print platform information for debugging."""
    info = [
        f"[INFO] Platform: {platform.platform()}",
        f"[INFO] System: {SYSTEM}",
        f"[INFO] Windows: {IS_WINDOWS}",
        f"[INFO] Linux: {IS_LINUX}",
        f"[INFO] macOS: {IS_MACOS}",
        f"[INFO] Android: {IS_ANDROID}",
        f"[INFO] Termux: {IS_TERMUX}",
        f"[INFO] WSL: {IS_WSL}",
        f"[INFO] Python: {platform.python_version()}",
        f"[INFO] Line endings: {LINE_ENDINGS}",
    ]

    if verbose:
        info.extend([
            f"[INFO] Current dir: {Path.cwd()}",
            f"[INFO] Home dir: {Path.home()}",
            f"[INFO] Executable: {sys.executable}",
            f"[INFO] Architecture: {platform.architecture()[0]}",
            f"[INFO] Machine: {platform.machine()}",
        ])

    print("\n".join(info))


# ----------------------------- Templates -----------------------------------

def template_actions(name: str, root: Path, vars_: Dict[str, str]) -> List[Action]:
    """
    Generate template-based actions.
    
    Args:
        name: Template name
        root: Root directory for generated files
        vars_: Variables for template expansion
        
    Returns:
        List of actions to create template structure
    """
    name = name.lower().strip()
    acts: List[Action] = []

    if name in ("python-cli", "py-cli"):
        acts.extend([
            Action("mkdir", root / "src"),
            Action("write", root / "src" / "__init__.py", ""),
            Action(
                "write",
                root / "src" / "main.py",
                normalize_line_endings(
                    textwrap.dedent(
                        f"""\
                        #!/usr/bin/env python3
                        \"\"\"{expand_vars('${PROJECT}', vars_) or 'App'} - {expand_vars('${DESCRIPTION}', vars_) or 'CLI application'}\"\"\"

                        def main():
                            print("Hello {expand_vars('${AUTHOR}', vars_) or 'World'}!")

                        if __name__ == "__main__":
                            main()
                        """
                    )
                ),
            ),
            Action("chmod", root / "src" / "main.py", mode=0o755),
            Action(
                "write",
                root / "README.md",
                f"# {expand_vars('${PROJECT}', vars_) or 'App'}\n\n"
                f"{expand_vars('${DESCRIPTION}', vars_) or 'A minimal Python CLI.'}\n",
            ),
            Action(
                "write",
                root / ".gitignore",
                "__pycache__/\n.venv/\n.DS_Store\n*.pyc\n*.pyo\n*.pyd\n",
            ),
            Action(
                "write",
                root / "pyproject.toml",
                textwrap.dedent(
                    f"""\
                    [project]
                    name = "{expand_vars('${PKG}', vars_) or 'app'}"
                    version = "{expand_vars('${VERSION}', vars_) or '0.1.0'}"
                    description = "{expand_vars('${DESCRIPTION}', vars_) or 'CLI application'}"
                    authors = [{{name = "{expand_vars('${AUTHOR}', vars_) or 'Unknown'}"}}]
                    requires-python = ">=3.8"

                    [project.scripts]
                    {expand_vars('${PKG}', vars_) or 'app'} = "src.main:main"
                    """
                ),
            ),
        ])
    elif name in ("node-cli", "js-cli"):
        acts.extend([
            Action("mkdir", root / "bin"),
            Action(
                "write",
                root / "bin" / "cli.js",
                normalize_line_endings(
                    "#!/usr/bin/env node\nconsole.log('Hello CLI');\n"
                ),
            ),
            Action("chmod", root / "bin" / "cli.js", mode=0o755),
            Action(
                "write",
                root / "package.json",
                normalize_line_endings(
                    textwrap.dedent(
                        f"""\
                        {{
                          "name": "{expand_vars('${PKG}', vars_) or 'app'}",
                          "version": "{expand_vars('${VERSION}', vars_) or '0.1.0'}",
                          "description": "{expand_vars('${DESCRIPTION}', vars_) or 'CLI application'}",
                          "bin": "bin/cli.js",
                          "author": "{expand_vars('${AUTHOR}', vars_) or ''}"
                        }}
                        """
                    )
                ),
            ),
            Action(
                "write",
                root / ".gitignore",
                "node_modules/\n.DS_Store\nnpm-debug.log*\n",
            ),
            Action(
                "write",
                root / "README.md",
                f"# {expand_vars('${PROJECT}', vars_) or 'Node CLI'}\n",
            ),
        ])
    elif name in ("rust-cli", "rs-cli"):
        acts.extend([
            Action(
                "write",
                root / "Cargo.toml",
                textwrap.dedent(
                    f"""\
                    [package]
                    name = "{expand_vars('${PKG}', vars_) or 'app'}"
                    version = "{expand_vars('${VERSION}', vars_) or '0.1.0'}"
                    authors = ["{expand_vars('${AUTHOR}', vars_) or 'Unknown'}"]
                    description = "{expand_vars('${DESCRIPTION}', vars_) or 'CLI application'}"

                    [[bin]]
                    name = "{expand_vars('${PKG}', vars_) or 'app'}"
                    path = "src/main.rs"
                    """
                ),
            ),
            Action("mkdir", root / "src"),
            Action(
                "write",
                root / "src" / "main.rs",
                textwrap.dedent(
                    """\
                    fn main() {
                        println!("Hello, Rust CLI!");
                    }
                    """
                ),
            ),
        ])
    else:
        # Unknown template - create basic structure
        acts.append(
            Action(
                "write",
                root / "README.md",
                f"# {name}\n\nProject generated from template: {name}\n",
            )
        )

    return acts


# ----------------------------- Parsing -------------------------------------

class ParserState:
    """State maintained during schema parsing."""

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
        self.heredoc_stack: List[Tuple[str, Path, int]] = (
            []
        )  # (marker, target_path, start_line)
        self.trusted_templates: Optional[Set[str]] = None
        self.base_dir: Path = out_root

    def current_dir(self) -> Path:
        """Get current directory from stack."""
        return self.dir_stack[-1]


def parse_schema(
    schema_text: str, out_root: Path, base_dir: Path, verbose: bool = False
) -> Tuple[List[Action], Dict[str, Optional[str]], Dict[str, str]]:
    """
    Parse schema text into actions, metadata, and variables.
    
    Args:
        schema_text: Schema content as string
        out_root: Root directory for output
        base_dir: Base directory for relative includes
        verbose: Enable verbose output
        
    Returns:
        Tuple of (actions, metadata, variables)
        
    Raises:
        ParseError: If schema parsing fails
    """
    st = ParserState(out_root)
    st.base_dir = base_dir
    st.trusted_templates = load_trusted_templates(base_dir)
    lines = schema_text.splitlines()

    # First pass: extract metadata and variables
    _extract_metadata_and_vars(lines, st, verbose)

    # Second pass: parse structure
    i = 0
    while i < len(lines):
        try:
            i = _parse_line(lines, i, st, base_dir, verbose)
        except ParseError:
            raise
        except Exception as e:
            raise ParseError(
                i + 1, f"Unexpected error: {e}", lines[i] if i < len(lines) else ""
            )

    # Apply ignore patterns
    if st.ignores:
        st.actions = _filter_ignored_actions(st.actions, st.ignores, verbose)

    return coalesce_mkdirs(st.actions), st.meta, st.vars


def _extract_metadata_and_vars(lines: List[str], st: ParserState, verbose: bool) -> None:
    """Extract metadata comments and variable directives in first pass."""
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip():
            continue

        stripped = line.strip()

        # Metadata comments
        if stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            for key in ("Project", "Description", "Version"):
                pref = f"{key}:"
                if body.lower().startswith(pref.lower()):
                    val = body[len(pref):].strip()
                    if val:
                        st.meta[key] = val
                        # Also set corresponding variable
                        st.vars[key.upper()] = val
                        if verbose:
                            print(f"[META] {key}: {val}")
            continue

        # Variable directives
        if stripped.startswith("@set "):
            try:
                body = stripped[len("@set "):].strip()
                if "=" not in body:
                    continue
                k, v = body.split("=", 1)
                key = k.strip()
                value = v.strip()
                st.vars[key] = value
                if verbose:
                    print(f"[VAR] @set {key} = {value}")
            except Exception:
                continue  # Silently skip malformed @set in first pass


def _parse_line(
    lines: List[str], index: int, st: ParserState, base_dir: Path, verbose: bool
) -> int:
    """Parse a single line and return next line index."""
    raw = lines[index]
    line_num = index + 1

    if not raw.strip():
        return index + 1

    if raw.lstrip().startswith("#"):
        return index + 1

    # Handle directives
    stripped = raw.strip()
    if stripped.startswith("@"):
        return _handle_directive(stripped, st, base_dir, line_num, verbose, index)

    # Handle heredoc continuation
    if st.heredoc_stack:
        return _handle_heredoc_continuation(raw, lines, index, st, line_num, verbose)

    # Parse indentation and adjust directory stack
    leading_spaces = len(raw) - len(raw.lstrip())
    _adjust_directory_stack(leading_spaces, st)

    entry = raw.strip()

    # Handle different entry types
    if entry.startswith("/"):
        return _handle_absolute_section(entry, st, line_num, verbose)
    elif entry.endswith("/") and "->" not in entry and "<<" not in entry:
        return _handle_directory(entry, leading_spaces, st, line_num, verbose)
    elif "<<" in entry:
        return _handle_heredoc_start(entry, lines, index, st, line_num, verbose)
    elif "->" in entry:
        return _handle_inline_file(entry, st, line_num, verbose)
    else:
        return _handle_plain_file(entry, st, line_num, verbose)


def _adjust_directory_stack(leading_spaces: int, st: ParserState) -> None:
    """Adjust directory stack based on indentation changes."""
    # Pop stack until we find matching indentation level
    while st.indent_stack and leading_spaces < st.indent_stack[-1]:
        st.indent_stack.pop()
        st.dir_stack.pop()

    # Push new level if indentation increased
    if leading_spaces > st.indent_stack[-1]:
        st.indent_stack.append(leading_spaces)


def _handle_absolute_section(
    entry: str, st: ParserState, line_num: int, verbose: bool
) -> int:
    """Handle absolute section starting with /."""
    section = entry.lstrip("/")
    if section.endswith("/"):
        section = section[:-1]

    section = expand_vars(section, st.vars)
    new_dir = st.out_root / Path(section)
    st.actions.append(Action("mkdir", new_dir))

    # Update directory stack
    if st.indent_stack[-1] == (len(entry) - len(entry.lstrip())):
        st.dir_stack[-1] = new_dir
    else:
        st.dir_stack.append(new_dir)

    if verbose:
        print(f"[PARSE] L{line_num}: enter /{section}")
    return line_num


def _handle_directory(
    entry: str, leading_spaces: int, st: ParserState, line_num: int, verbose: bool
) -> int:
    """Handle directory declaration."""
    dir_name = expand_vars(entry[:-1].strip(), st.vars)
    new_dir = st.current_dir() / dir_name
    st.actions.append(Action("mkdir", new_dir))

    # Update directory stack
    if st.indent_stack and (leading_spaces > st.indent_stack[-1]):
        st.dir_stack.append(new_dir)
    else:
        st.dir_stack[-1] = new_dir

    if verbose:
        print(f"[PARSE] L{line_num}: dir {new_dir}")
    return line_num


def _handle_heredoc_start(
    entry: str,
    lines: List[str],
    index: int,
    st: ParserState,
    line_num: int,
    verbose: bool,
) -> int:
    """Handle heredoc start with <<."""
    left, marker = entry.split("<<", 1)
    file_name = expand_vars(left.strip(), st.vars)
    marker = marker.strip() or "EOF"
    target_path = st.current_dir() / file_name

    # Security check for file extensions
    if not validate_file_extension(file_name):
        raise ParseError(
            line_num, f"Potentially dangerous file extension: {file_name}", entry
        )

    # Start heredoc parsing
    st.heredoc_stack.append((marker, target_path, line_num))
    return index + 1


def _handle_heredoc_continuation(
    raw: str,
    lines: List[str],
    index: int,
    st: ParserState,
    line_num: int,
    verbose: bool,
) -> int:
    """Handle lines within a heredoc block."""
    if not st.heredoc_stack:
        return index + 1

    marker, target_path, start_line = st.heredoc_stack[-1]

    # Check for heredoc end marker
    if raw.strip() == marker:
        # End of heredoc - create the file
        content_lines = lines[start_line:index]
        content = "\n".join(content_lines)
        content = expand_vars(content, st.vars)
        content = normalize_line_endings(content)

        st.actions.append(Action("write", target_path, content))

        # Add executable permission for script files
        if not IS_WINDOWS and target_path.suffix in (".sh", ".py", ".pl", ".rb"):
            st.actions.append(Action("chmod", target_path, mode=0o755))

        if verbose:
            print(
                f"[PARSE] L{start_line}-{line_num-1}: heredoc {target_path} ({len(content)} bytes)"
            )

        st.heredoc_stack.pop()
        return index + 1
    else:
        # Continue collecting heredoc content
        return index + 1


def _handle_inline_file(
    entry: str, st: ParserState, line_num: int, verbose: bool
) -> int:
    """Handle inline file with -> syntax."""
    left, right = entry.split("->", 1)
    file_name = expand_vars(left.strip(), st.vars)
    content = expand_vars(right.lstrip(), st.vars)
    content = normalize_line_endings(content)

    # Security check
    if not validate_file_extension(file_name):
        raise ParseError(
            line_num, f"Potentially dangerous file extension: {file_name}", entry
        )

    target_path = st.current_dir() / file_name
    st.actions.append(Action("write", target_path, content))

    # Add executable permission for script files
    if not IS_WINDOWS and target_path.suffix in (".sh", ".py", ".pl", ".rb"):
        st.actions.append(Action("chmod", target_path, mode=0o755))

    if verbose:
        print(f"[PARSE] L{line_num}: file {target_path} (inline, {len(content)} chars)")
    return line_num + 1


def _handle_plain_file(
    entry: str, st: ParserState, line_num: int, verbose: bool
) -> int:
    """Handle plain file declaration."""
    file_name = expand_vars(entry, st.vars)

    # Security check
    if not validate_file_extension(file_name):
        raise ParseError(
            line_num, f"Potentially dangerous file extension: {file_name}", entry
        )

    target_path = st.current_dir() / file_name

    # Ensure parent directory exists
    st.actions.append(Action("mkdir", target_path.parent))
    st.actions.append(Action("write", target_path, ""))

    # Add executable permission for script files
    if not IS_WINDOWS and target_path.suffix in (".sh", ".py", ".pl", ".rb"):
        st.actions.append(Action("chmod", target_path, mode=0o755))

    if verbose:
        print(f"[PARSE] L{line_num}: file {target_path} (empty)")
    return line_num + 1


def _handle_directive(
    line: str, st: ParserState, base_dir: Path, line_num: int, verbose: bool, index: int
) -> int:
    """Handle @ directives."""
    try:
        if line.startswith("@set "):
            body = line[len("@set "):].strip()
            if "=" not in body:
                raise ParseError(
                    line_num, "Invalid @set syntax, use: @set KEY=VALUE", line
                )
            k, v = body.split("=", 1)
            key = k.strip()
            value = v.strip()
            st.vars[key] = value
            if verbose:
                print(f"[DIRECTIVE] @set {key} = {value}")

        elif line.startswith("@include "):
            inc_file = expand_vars(line[len("@include "):].strip(), st.vars)
            inc_path = (base_dir / inc_file).resolve()

            # Security check for included files
            if not is_safe_under_base(inc_path, base_dir):
                raise ParseError(
                    line_num, f"Included file path traversal detected: {inc_file}", line
                )

            if not inc_path.exists():
                raise ParseError(line_num, f"Included file not found: {inc_file}", line)

            verify_include_signature(inc_path, line_num, line, verbose)

            included_text = inc_path.read_text(encoding="utf-8")
            included_actions, _, included_vars = parse_schema(
                included_text, st.out_root, inc_path.parent, verbose
            )
            st.actions.extend(included_actions)
            st.vars.update(included_vars)  # Merge variables
            if verbose:
                print(f"[DIRECTIVE] @include {inc_path}")

        elif line.startswith("@ignore"):
            patterns = line.split()[1:]
            st.ignores.extend(patterns)
            if verbose:
                print(f"[DIRECTIVE] @ignore {patterns}")

        elif line.startswith("@chmod "):
            rest = line[len("@chmod "):].strip()
            parts = rest.split()
            if len(parts) < 2:
                raise ParseError(
                    line_num, "Invalid @chmod syntax, use: @chmod PATH MODE", line
                )
            path_str = parts[0]
            mode_str = parts[1]
            target_path = st.out_root / expand_vars(path_str, st.vars)
            mode = _parse_chmod_mode(mode_str)
            st.actions.append(Action("chmod", target_path, mode=mode))
            if verbose:
                print(f"[DIRECTIVE] @chmod {target_path} {oct(mode)}")

        elif line.startswith("@copy "):
            rest = line[len("@copy "):].strip()
            parts = rest.split()
            if len(parts) < 2:
                raise ParseError(
                    line_num, "Invalid @copy syntax, use: @copy SRC DEST", line
                )
            src_str, dest_str = parts[0], parts[1]
            src_path = (base_dir / expand_vars(src_str, st.vars)).resolve()
            dest_path = (st.out_root / expand_vars(dest_str, st.vars)).resolve()

            # Security checks
            if not is_safe_under_base(src_path, base_dir):
                raise ParseError(
                    line_num, f"Copy source path traversal detected: {src_str}", line
                )
            if not is_safe_under_base(dest_path, st.out_root):
                raise ParseError(
                    line_num,
                    f"Copy destination path traversal detected: {dest_str}",
                    line,
                )

            if not src_path.exists():
                raise ParseError(line_num, f"Copy source not found: {src_path}", line)
            st.actions.append(Action("copy", dest_path, src=src_path))
            if verbose:
                print(f"[DIRECTIVE] @copy {src_path} -> {dest_path}")

        elif line.startswith("@template "):
            name = line[len("@template "):].strip()
            if st.trusted_templates is not None and name not in st.trusted_templates:
                raise ParseError(line_num, f"Template '{name}' is not trusted", line)
            template_acts = template_actions(name, st.out_root, st.vars)
            st.actions.extend(template_acts)
            if verbose:
                print(f"[DIRECTIVE] @template {name} ({len(template_acts)} actions)")

        elif line.startswith("@symlink "):
            rest = line[len("@symlink "):].strip()
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

            # Security check
            if not is_safe_under_base(link_path, st.out_root):
                raise ParseError(
                    line_num, f"Symlink path traversal detected: {link_str}", line
                )

            st.actions.append(Action("symlink", link_path, target=target_path))
            if verbose:
                print(f"[DIRECTIVE] @symlink {target_path} -> {link_path}")

        else:
            raise ParseError(line_num, f"Unknown directive: {line.split()[0]}", line)

    except ParseError:
        raise
    except Exception as e:
        raise ParseError(line_num, f"Directive error: {e}", line)

    return index + 1


def _parse_chmod_mode(mode_str: str) -> int:
    """Parse chmod mode string into integer."""
    if mode_str.startswith("+"):
        if "x" in mode_str:
            return 0o755
        elif "w" in mode_str:
            return 0o644
        else:
            return 0o644
    else:
        try:
            if mode_str.startswith("0o"):
                return int(mode_str, 8)
            else:
                return int(mode_str, 8)
        except ValueError:
            # Default to readable
            return 0o644


def _filter_ignored_actions(
    actions: List[Action], ignores: List[str], verbose: bool
) -> List[Action]:
    """Filter actions based on ignore patterns."""
    filtered = []
    for act in actions:
        skip = False
        rel_path = str(act.path)
        for pattern in ignores:
            if pattern in rel_path or fnmatch.fnmatch(rel_path, pattern):
                skip = True
                if verbose:
                    print(f"[FILTER] ignore {act.path} (pattern: {pattern})")
                break
        if not skip:
            filtered.append(act)
    return filtered


def coalesce_mkdirs(actions: List[Action]) -> List[Action]:
    """Remove redundant mkdir actions."""
    seen_dirs = set()
    result = []

    for act in actions:
        if act.kind == "mkdir":
            if act.path not in seen_dirs:
                seen_dirs.add(act.path)
                result.append(act)
        else:
            result.append(act)

    return result


# ----------------------------- Realization ---------------------------------

def realize(
    actions: List[Action],
    base_dir: Path,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> GenerationResult:
    """
    Execute actions to create the repository structure with enhanced security.
    
    Args:
        actions: List of actions to perform
        base_dir: Base directory for security checks
        dry_run: If True, only show what would be done
        force: If True, overwrite existing files
        verbose: Enable verbose output
        
    Returns:
        GenerationResult with success status and messages
    """
    success = True
    actions_performed = 0
    errors: List[str] = []
    warnings: List[str] = []

    for act in actions:
        try:
            # Enhanced security check
            if not is_safe_under_base(act.path, base_dir):
                error_msg = f"Skipping unsafe path: {act.path}"
                errors.append(error_msg)
                if verbose:
                    print(f"[SECURITY] {error_msg}")
                continue

            if act.kind == "mkdir":
                if verbose or dry_run:
                    print(f"[{'DRY' if dry_run else 'MKDIR'}] {act.path}")
                if not dry_run:
                    act.path.mkdir(parents=True, exist_ok=True)
                    actions_performed += 1

            elif act.kind == "write":
                if verbose or dry_run:
                    size = len(act.content or "")
                    print(
                        f"[{'DRY' if dry_run else 'WRITE'}] {act.path} ({size} bytes)"
                    )
                if not dry_run:
                    if act.path.exists() and not force:
                        warning_msg = f"Skipping existing file (use --force to overwrite): {act.path}"
                        warnings.append(warning_msg)
                        if verbose:
                            print(f"[WARN] {warning_msg}")
                        continue
                    act.path.parent.mkdir(parents=True, exist_ok=True)
                    act.path.write_text(act.content or "", encoding="utf-8")
                    actions_performed += 1

            elif act.kind == "chmod":
                if verbose or dry_run:
                    print(
                        f"[{'DRY' if dry_run else 'CHMOD'}] {act.path} {oct(act.mode or 0o644)}"
                    )
                if not dry_run and not IS_WINDOWS:
                    act.path.chmod(act.mode or 0o644)
                    actions_performed += 1

            elif act.kind == "copy":
                if verbose or dry_run:
                    print(f"[{'DRY' if dry_run else 'COPY'}] {act.src} -> {act.path}")
                if not dry_run:
                    if act.path.exists() and not force:
                        warning_msg = f"Skipping existing file (use --force to overwrite): {act.path}"
                        warnings.append(warning_msg)
                        if verbose:
                            print(f"[WARN] {warning_msg}")
                        continue

                    # Security check for copy source
                    if not is_safe_under_base(act.src, base_dir):
                        error_msg = f"Skipping unsafe copy source: {act.src}"
                        errors.append(error_msg)
                        if verbose:
                            print(f"[SECURITY] {error_msg}")
                        continue

                    act.path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(act.src, act.path)
                    actions_performed += 1

            elif act.kind == "symlink":
                if verbose or dry_run:
                    print(
                        f"[{'DRY' if dry_run else 'SYMLINK'}] {act.target} -> {act.path}"
                    )
                if not dry_run:
                    if act.path.exists():
                        if force:
                            act.path.unlink()
                        else:
                            warning_msg = f"Skipping existing symlink (use --force to overwrite): {act.path}"
                            warnings.append(warning_msg)
                            if verbose:
                                print(f"[WARN] {warning_msg}")
                            continue
                    act.path.parent.mkdir(parents=True, exist_ok=True)
                    act.path.symlink_to(act.target)
                    actions_performed += 1

        except Exception as e:
            error_msg = f"Failed to {act.kind} {act.path}: {e}"
            errors.append(error_msg)
            print(f"[ERROR] {error_msg}")
            success = False

    return GenerationResult(
        success=success and len(errors) == 0,
        actions_performed=actions_performed,
        errors=errors,
        warnings=warnings,
    )


# ----------------------------- Bootstrap -----------------------------------

def detect_install_bin() -> Path:
    """Detect appropriate bin directory for installation."""
    if IS_TERMUX:
        return Path("/data/data/com.termux/files/usr/bin")
    elif IS_WINDOWS:
        # Try common Windows locations
        for candidate in [
            Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps",
            Path.home() / "AppData" / "Local" / "Programs" / "Python",
            Path.home() / "AppData" / "Local" / "bin",
        ]:
            if candidate.exists():
                return candidate
        return Path.home() / "AppData" / "Local" / "bin"
    else:
        # Unix-like systems
        return Path.home() / ".local" / "bin"


def persist_path(bin_dir: Path, verbose: bool = False) -> None:
    """Persist PATH configuration for various shells."""
    export_line = f'export PATH="{bin_dir}:$PATH"'

    shell_rc_files = {
        "zsh": [Path.home() / ".zshrc", Path.home() / ".zprofile"],
        "bash": [
            Path.home() / ".bashrc",
            Path.home() / ".bash_profile",
            Path.home() / ".profile",
        ],
        "fish": [Path.home() / ".config" / "fish" / "config.fish"],
        "default": [Path.home() / ".profile"],
    }

    def add_to_file(file_path: Path, content: str):
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch(exist_ok=True)

            current_content = file_path.read_text(encoding="utf-8")
            if content not in current_content:
                with file_path.open("a", encoding="utf-8") as f:
                    f.write(f"\n# Added by lrc bootstrap\n{content}\n")
                if verbose:
                    print(f"[PATH] Added to {file_path}")
            else:
                if verbose:
                    print(f"[PATH] Already in {file_path}")
        except Exception as e:
            if verbose:
                print(f"[WARN] Could not update {file_path}: {e}")

    # Detect shell and update appropriate files
    shell = (
        os.environ.get("SHELL", "").split("/")[-1]
        if "SHELL" in os.environ
        else "default"
    )

    target_files = shell_rc_files.get(shell, shell_rc_files["default"])
    for rc_file in target_files:
        add_to_file(rc_file, export_line)


def do_bootstrap(argv0: str, verbose: bool = False) -> Path:
    """
    Bootstrap installation of lrc to user bin directory.
    
    Args:
        argv0: Path to current script
        verbose: Enable verbose output
        
    Returns:
        Path to installed executable
        
    Raises:
        Exception: If installation fails
    """
    bin_dir = detect_install_bin()
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Determine target name
    target_name = "lrc.exe" if IS_WINDOWS else "lrc"
    target_path = bin_dir / target_name

    # Copy current script
    source_path = Path(argv0).resolve()
    if not source_path.exists():
        # Fallback to __file__
        source_path = Path(__file__).resolve()

    print(f"[BOOTSTRAP] Installing lrc to {target_path}")

    try:
        shutil.copy2(source_path, target_path)

        # Make executable on Unix-like systems
        if not IS_WINDOWS:
            target_path.chmod(0o755)

        print(f"[SUCCESS] Installed to {target_path}")

        # Update PATH configuration
        persist_path(bin_dir, verbose)
        print(f"[PATH] Added {bin_dir} to PATH configuration")
        print(f"[INFO] Restart your shell or run: source ~/.profile")

        return target_path

    except Exception as e:
        print(f"[ERROR] Installation failed: {e}")
        raise


# ----------------------------- Main CLI ------------------------------------

def main() -> int:
    """Compatibility wrapper around the refactored CLI module."""
    from .cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
