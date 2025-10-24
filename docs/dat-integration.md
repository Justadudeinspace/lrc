# DAT Integration Guide

LRC can trigger the DAT auditing pipeline immediately after a successful repository build. This guide explains the configuration surface.

## 1. Configure DAT

Create `~/.config/lrc/dat_integration.json`:

```json
{
  "enabled": true,
  "command": ["dat", "audit", "--report", "${BUILD_DIR}"],
  "env": {
    "DAT_API_TOKEN": "example-token"
  }
}
```

- `enabled`: toggles the audit step
- `command`: a string or array executed after the build. `${BUILD_DIR}` is replaced with the output directory.
- `env`: optional environment variables added to the subprocess.

## 2. Run the compiler

```bash
lrc examples/dat_integration.lrc -o ./build/dat --audit
```

The CLI prints `[AUDIT]` messages summarising DAT output. Failures surface as warnings without deleting the generated repository.

## 3. Troubleshooting

| Symptom | Resolution |
|---------|------------|
| `DAT command not found` | Ensure the binary referenced by `command` exists on `PATH`. |
| Exit code non-zero | Review the logged stdout/stderr. LRC continues but reports the failure. |
| Config parse error | Validate the JSON in `dat_integration.json` (comments are not supported). |
