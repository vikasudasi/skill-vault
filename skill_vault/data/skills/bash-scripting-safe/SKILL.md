---
name: bash-scripting-safe
description: Write safe, robust Bash scripts — set -euo pipefail, quoting, word splitting, error handling, idempotency, and common data-loss gotchas.
tags: [bash, shell, scripting, devops, linux]
triggers: [bash, shell script, shellcheck, write a script]
complexity: low
time_estimate: 30-60 min
prerequisites: [linux or macos terminal]
source: Skill Vault curated library
verify: true
---

# Safe Bash Scripting

Use when writing a shell script that must not corrupt files, delete the wrong
thing, or silently fail. Bash is powerful precisely because it's dangerous — the
discipline below is what makes it safe.

## Always start with these three lines

```bash
#!/usr/bin/env bash
set -euo pipefail
```

- `-e` — exit on first failing command (no silent mid-script failure).
- `-u` — error on unset variable (catches typos like `$file` vs `$files`).
- `-o pipefail` — a failing command anywhere in a pipeline fails the pipeline.

Add `IFS=$'\n\t'` when you parse output: it changes Bash's default word-splitting
(space, tab, newline) to just newline + tab, so filenames containing spaces no
longer get split into multiple arguments.

## Quote everything (word splitting is the #1 data-loss path)

```bash
dir="$1"                          # quote expansions
for f in "$dir"/*.txt; do         # quotes + glob
  cp "$f" "$dest/"
done
```

Unquoted `$var` undergoes **word splitting** (splits on spaces) and **globbing**
(* and ? expand). The classic disaster:

```bash
# WRONG — if "$file" contains a space, rm deletes multiple files; glob expansion is worse
rm $file

# RIGHT
rm -- "$file"
```

A variable is only safe unquoted when you *intend* splitting/globbing. Prefer
`"$@"`-style quoting everywhere else.

## Redirects and atomic file writes

- Use a temp file + `mv` for atomic writes; never `>` straight onto a file
  you also read later in the same script (it truncates the input mid-run):

```bash
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT          # clean up scratch even on error
grep foo input.txt > "$tmp"
mv "$tmp" output.txt              # atomic swap
```

- `mktemp` for scratch files (safer than hard-coded `/tmp/name` which can collide
  or be a symlink). `trap ... EXIT` guarantees cleanup on failure.
- Beware `set -e` + empty globs: `"$dir"/*.txt` with no matches stays a literal
  `*.txt` string — check with `shopt -s nullglob` or test existence.

## Error handling

```bash
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi
```

- Print errors to **stderr** (`>&2`), not stdout, so messages don't pollute a
  script's machine-readable stdout output.
- Check the exit status of anything whose failure matters:

```bash
if ! git fetch origin; then
  echo "fetch failed" >&2
  exit 1
fi
```

## Idempotency

Make scripts safe to re-run: create-if-absent rather than fail-if-exists,
`mkdir -p` instead of `mkdir`, and guard destructive steps. A script that
destroys state on the second run is a trap.

## Pitfalls

- **`set -e` does not always trigger** inside `if`/`&&`/`||` conditions or on a
  command whose return you're checking — that's expected. Only rely on `-e` for
  statements you are *not* explicitly testing.
- **`set -e` inside functions**: a function's last command's status is its
  return value; a "failing" line in a function can be masked. Return/exit
  explicitly.
- **`set -u` + positional args**: `$1` unset errors; guard with
  `[ $# -ge 1 ]` or `${1:?usage}`.
- **Passwords/secrets never via `-x`**: running `set -x` (trace) or echoing
  `${VAR}` leaks secrets into logs. Never `export` secrets you don't need in
  child processes.
- **Always run `shellcheck`** on anything non-trivial (CI-friendly, catches all
  of the above). Bash is subtle; human review misses what shellcheck flags.

## Checklist

- [ ] `set -euo pipefail` present at the top (plus `IFS` when parsing output).
- [ ] Every expansion quoted unless splitting is intentional.
- [ ] Temp file + `mv` for atomic writes; `mktemp` + `trap` cleanup.
- [ ] Errors to `>&2`; critical commands' exit statuses checked.
- [ ] Idempotent on re-run.
- [ ] `shellcheck` clean.