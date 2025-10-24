<p align="center">
  <img src="./docs/assets/lrc-logo-green.png" alt="LRC — Local Repo Compile" width="600">
</p>

# ⚙️ LRC — Local Repo Compile

**LRC** (Local Repo Compiler) turns declarative `.lrc` schema files into complete, production-ready repositories. Version **v1.0.0-alpha.1** introduces a modular architecture, DAT audit integration, and enterprise security features such as template trust policies and GPG validation for imported schemas.

---

## ✨ Highlights

- ✅ Modular runtime (`parser`, `compiler`, `generator`, `cli`) under `src/lrc`
- ✅ Robust schema language with heredocs, variable expansion, and nested directives
- ✅ Trusted template policy via `trusted_templates.json`
- ✅ Optional DAT post-build auditing via `--audit`
- ✅ Cross-platform bootstrap for Linux, macOS, Windows, WSL, and Termux
- ✅ Python **3.9 → 3.13** compatibility with automated linting, typing, and tests

---

## 🚀 Quick Start

### Install
```bash
# Clone & bootstrap dependencies
git clone https://github.com/Justadudeinspace/lrc.git
cd lrc
chmod +x install_deps.sh
./install_deps.sh

# Optional: install the CLI into ~/.local/bin (or platform equivalent)
python -m lrc --bootstrap
```

### Compile a schema
```bash
# Generate a repo from a schema file
lrc schema_example.lrc -o ./generated

# Preview actions without touching disk
lrc schema_example.lrc --dry-run

# Force overwrites and run DAT audit afterwards
lrc schema_example.lrc -o ./generated --force --audit
```

> **Tip:** `lrc --platform-info` prints environment diagnostics useful for troubleshooting cross-platform quirks.

---

## 🧩 Schema Language Essentials

### Metadata & variables
```text
# Project: Demo Service
# Description: REST API scaffold
# Version: 1.0.0

@set AUTHOR=Acme
@set DESCRIPTION=Internal tooling
```

Use `${VARIABLE}` anywhere in paths, filenames, or file contents.

### File expressions
```text
src/              # create directories recursively
README.md         # empty file
config.json -> {"debug": false}               # inline file
script.py <<PY                                # heredoc file
#!/usr/bin/env python3
print("Hello ${AUTHOR}")
PY
```

### Directives
| Directive | Description |
|-----------|-------------|
| `@set KEY=VALUE` | Define variables in the parser scope |
| `@ignore pattern` | Skip actions whose paths match `fnmatch` patterns |
| `@template name` | Render a trusted template (validated via `trusted_templates.json`) |
| `@chmod path mode` | Apply a POSIX mode (e.g. `0o755`) |
| `@include file` | Include another `.lrc` file (GPG signature validated when present) |
| `@copy src dest` | Copy an existing file into the build output |
| `@symlink target link` | Create symbolic links |

> Place `trusted_templates.json` beside your schema (or in `~/.config/lrc/`) to extend the allow-list. Attempting to use untrusted templates raises a `ParseError` with contextual hints.

---

## 🔐 Security & Trust

### Template trust policy
LRC reads `trusted_templates.json` from:
1. The schema directory or `.lrc/` subdirectory
2. `~/.config/lrc/trusted_templates.json`
3. The repository default (see `trusted_templates.json` in the project root)

Only templates listed in the allow-list may be rendered. Attempting to use an untrusted template aborts the build with a red, contextual error message.

### GPG-validated includes
When an included schema has a sibling signature file (`.asc` or `.sig`), LRC verifies the signature with `gpg --verify`. Set `LRC_REQUIRE_SIGNED_INCLUDES=1` to require signatures for every `@include`. Invalid or missing signatures raise descriptive `ParseError`s that highlight the offending line in the source schema.

---

## 🧰 CLI Reference
```
lrc SCHEMA [OPTIONS]

Options:
  -o, --output PATH    Override output directory
  --base-dir PATH      Base directory for resolving includes
  --dry-run            Preview actions without writing to disk
  --force              Overwrite existing files
  --audit              Run the DAT audit pipeline after a successful build
  -v, --verbose        Emit verbose logs and platform info
  --bootstrap          Install the CLI into the user PATH
  --platform-info      Dump environment diagnostics
  --version            Print version information
```

`--audit` reads `~/.config/lrc/dat_integration.json`:
```json
{
  "enabled": true,
  "command": ["dat", "audit", "--report", "${BUILD_DIR}"],
  "env": {"DAT_ENV": "production"}
}
```
If the file is absent, auditing is skipped with an informative message.

---

## 🔄 LRC → DAT Workflow Example
1. Author your schema (see [`examples/dat_integration.lrc`](./examples/dat_integration.lrc)).
2. Configure DAT integration in `~/.config/lrc/dat_integration.json`.
3. Compile the schema with `lrc examples/dat_integration.lrc -o ./build --audit`.
4. Inspect DAT output logged immediately after a successful build.

DAT command failures are surfaced with warnings while keeping the repository intact.

---

## 🧪 Quality Tooling

- `pytest` test suite covering parser, compiler, and CLI behaviours
- `mypy` static typing, `black` formatting, and coverage reporting via CI (`.github/workflows/lrc-build.yml`)
- Works on CPython 3.9, 3.10, 3.11, 3.12, and 3.13

Run locally:
```bash
pip install -e .[dev]
pytest
mypy src/lrc
black --check src tests
```

---

## 🆘 Troubleshooting

| Symptom | Resolution |
|---------|------------|
| `GPG executable not available` | Install `gpg` or unset `LRC_REQUIRE_SIGNED_INCLUDES`. |
| Template rejected as untrusted | Add the template to `trusted_templates.json` in the schema directory or config path. |
| DAT audit skipped | Ensure `~/.config/lrc/dat_integration.json` exists and `enabled` is `true`. |
| PATH not updated after `--bootstrap` | Re-run your shell or source the printed profile file. |

Use `lrc --platform-info` when reporting issues to include environment details.

---

## 🧽 Schema Lint Checklist

- [ ] Metadata (`# Project`, `# Description`, `# Version`) defined at the top
- [ ] Variables declared before use with `@set`
- [ ] Templates approved via `trusted_templates.json`
- [ ] Includes accompanied by `.asc` signatures when required
- [ ] Avoid trailing whitespace — indentation controls directory nesting

---

## 📚 Further Reading

- [`docs/getting-started.md`](./docs/getting-started.md) — step-by-step tutorial
- [`docs/dat-integration.md`](./docs/dat-integration.md) — configuring the DAT bridge
- [`docs/troubleshooting.md`](./docs/troubleshooting.md) — extended FAQ
- [`examples/`](./examples) — ready-to-run schemas for diverse stacks

---

© 2024 LRC contributors. Licensed under the MIT License.
