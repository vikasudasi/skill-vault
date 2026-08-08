---
name: git-workflow
description: Safe Git branch workflow — feature branches, rebase vs merge, interactive rebase, destructive-command guardrails.
tags: [git, version-control, workflow, github]
triggers: [git, branch, rebase, merge, squash, force push]
complexity: low
time_estimate: 20-40 min
prerequisites: [git]
source: Skill Vault curated library
verify: true
---

# Safe Git Branch Workflow

Use when managing feature branches and keeping history clean without losing work.

## Branch + commit flow

```bash
git switch -c feat/thing
git add -A
git commit -m "feat: add thing"
```

## Rebasing onto latest main (preferred over merge)

```bash
git fetch origin
git rebase origin/main
# resolve conflicts, then:
git push --force-with-lease
```

`--force-with-lease` refuses to clobber remote commits that changed since your
last fetch — always prefer it over `--force`.

## Interactive rebase to clean up

```bash
git rebase -i HEAD~5   # squash/fixup/reword
```

## Recovering from mistakes

- Accidental reset: `git reflog` then `git reset --hard <sha>`.
- Uncommitted work lost: `git stash` is the checkpoint; `git fsck --lost-found` as last resort.

## Guardrails

- Never `git push --force` on a shared branch others may have pulled.
- Never `git reset --hard` without a stash or reflog stake in the outcome.
- Commit messages: imperative mood, `type: subject` convention; avoid `&` and
  unbalanced quotes when a tool parses your output.

## Pitfalls

- Rebasing a branch that is already merged creates duplicate commits — check with the remote first.
- Long-lived branches drift: rebase frequently, not just before merge.
