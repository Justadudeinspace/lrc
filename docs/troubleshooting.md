# Troubleshooting

## Parser errors
- **`Template 'foo' is not trusted`** – add `"foo"` to `trusted_templates.json` in the schema directory or `~/.config/lrc/`.
- **`GPG executable not available for signature verification`** – install `gpg` or unset `LRC_REQUIRE_SIGNED_INCLUDES`.
- **`Included file not found`** – includes are resolved relative to `--base-dir` (defaults to the schema directory).

## DAT integration
- Check that `dat_integration.json` is valid JSON.
- Commands may be a string (`"dat audit"`) or array (`["dat", "audit"]`).
- LRC replaces `${BUILD_DIR}` tokens with the absolute build path.

## Bootstrap
- When running `lrc --bootstrap`, the installer appends to common shell rc files (`.bashrc`, `.zshrc`, `.profile`). Restart your shell afterwards.

## Getting help
Run `lrc --platform-info` and capture the output together with the failing schema snippet.
