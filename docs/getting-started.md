# Getting Started with LRC

This quick guide walks through compiling a repository from a declarative `.lrc` schema using the v1.0.0-alpha.1 toolchain.

## 1. Prepare your environment

```bash
python -m pip install --upgrade pip
pip install -e .[dev]
```

## 2. Author a schema

Create `quickstart.lrc`:

```text
# Project: Quickstart Service
# Description: Demo API scaffold

@set AUTHOR=Quick Start Team
src/
  __init__.py
  main.py <<PY
  from pathlib import Path

  def main() -> None:
      print("Hello from LRC!")

  if __name__ == "__main__":
      main()
PY
README.md -> # Quickstart Service
```

## 3. Compile

```bash
lrc quickstart.lrc -o ./build/quickstart
```

Use `--dry-run` to preview actions and `--audit` to run the DAT pipeline after a successful build.

## 4. Explore

```bash
tree build/quickstart
python build/quickstart/src/main.py
```

You're ready to extend the schema with directives such as `@template`, `@copy`, and `@include`.
