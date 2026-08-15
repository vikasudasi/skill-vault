# Exit Codes and Trap Patterns

## Exit code conventions

| Code | Meaning | When to use |
|------|---------|-------------|
| 0    | Success | Normal exit |
| 1    | General error | Catch-all for unexpected failures |
| 2    | Misuse | Wrong arguments, invalid flags |
| 126  | Not executable | Permission denied |
| 127  | Not found | Missing command/dependency |
| 130  | Ctrl+C | Script interrupted by SIGINT |

## Best trap patterns

```bash
# Clean up temp files on exit (normal or error)
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Chain traps for multiple signals
trap 'echo "Interrupted"; exit 130' INT TERM
trap 'echo "Cleaning up..."; kill $PID 2>/dev/null' EXIT
```

## `set -e` gotchas

- `set -e` does NOT trigger inside `if`, `while`, `||`, or `&&` — that's by design
- Use explicit `|| die` chains when you need guaranteed exit:
  ```bash
  result=$(dangerous_command) || die "Failed"
  ```
- In functions called from conditions, errors are silenced — extract the call:
  ```bash
  ok=$(my_func)
  if [[ "$ok" == "ready" ]]; then ...
  ```

## `set -u` workarounds

```bash
# Check if a variable is set without triggering -u
if [[ -n "${VAR+x}" ]]; then
    echo "VAR is set to '$VAR'"
fi

# Provide defaults
OUTPUT="${1:-/tmp/default}"
```
