---
name: bash-scripting-safe
description: Write safe, robust Bash scripts — set -euo pipefail, quoting, error handling, and common gotchas.
tags: [bash, shell, scripting, devops, linux]
triggers: [bash, shell script, shellcheck, write a script]
complexity: low
time_estimate: 20-40 min
prerequisites: [linux or macos terminal]
source: Skill Vault curated library
---

# Safe Bash Scripting

Use when writing a shell script that must not corrupt files or silently fail.

## Always start with these three lines

```bash
#!/usr/bin/env bash
set -euo pipefail
```

- `-e` exit on first error
- `-u` error on unset variable (catches typos)
- `-o pipefail` a failing command in a pipeline fails the pipeline

## Quote everything

```bash
dir="$1"                          # quote expansions
for f in "$dir"/*.txt; do         # quotes + glob
  cp "$f" "$dest/"
done
```

Unquoted `$var` splits on spaces and globs — the classic source of data loss
(`rm $files` can delete the wrong thing).

## Redirects and files

- Use a temp file + `mv` for atomic writes; never `>` straight onto a file you
  also read in the same script.
- Prefer `mktemp` for scratch files.

## Error handling

```bash
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi
```

## Pitfalls

- `set -e` does not always trigger inside `if`/`&&` or on a command whose return
  you're checking — that's expected, not a bug.
- Use `set +e`/`set -e` carefully around commands that legitimately fail.
- Run `shellcheck` on anything non-trivial.
