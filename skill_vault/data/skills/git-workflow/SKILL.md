---
name: git-workflow
description: Safe Git branch workflow — feature branches, rebase vs merge vs squash, interactive rebase, force-with-lease, reflog recovery, destructive-command guardrails.
tags: [git, version-control, workflow, github]
triggers: [git, branch, rebase, merge, squash, force push]
complexity: low
time_estimate: 30-60 min
prerequisites: [git]
source: Skill Vault curated library
verify: true
---

# Safe Git Branch Workflow

Use when managing feature branches and keeping history clean **without losing
work**. The whole point of the discipline is that every destructive command is
recoverable and no shared branch is ever rewritten out from under a teammate.

## Branch + commit flow

```bash
git switch -c feat/thing        # branch off main, off a fresh main
git add -A
git commit -m "feat: add thing"
```

Convention this house follows (and Skill Vault's own commit log uses): commit
messages in **imperative mood** (`add`, `fix`, `seed: ...`), `type: subject`
format, no trailing `&`, and no unbalanced quotes — because a tool parses your
output. Keep the subject under ~72 chars; put detail in the body.

## Rebase onto latest main (preferred over merge)

```bash
git fetch origin
git rebase origin/main
# resolve conflicts, re-add resolved files, then:
git rebase --continue
git push --force-with-lease
```

### What rebase actually does to the graph

Before (your branch `feat` forked from an old `main`):

```text
      A---B---C   feat
     /
D---E---F         main
```

After `git rebase origin/main`:

```text
              A'--B'--C'   feat
             /
D---E---F---G              main   <- G is origin/main's newest
```

Your commits are `A B C` **re-played as new commits** `A' B' C'` on top of the
current main tip `G`. They keep the same content/message but get new SHAs.
Merging instead produces a visible `M` merge commit and keeps the fork point —
fine for shared branches, noise for solo work. Prefer rebase for a linear,
readable history on a branch only you own.

## `--force-with-lease` vs `--force`

- `git push --force` — overwrites the remote ref unconditionally. On a shared
  branch this **permanently deletes whatever a teammate pushed since your last
  fetch**. There is no remote-side undo.
- `git push --force-with-lease` — only overwrites if the remote tip still
  matches what you last fetched. If someone pushed in between, it **refuses**
  and tells you to fetch again first.

**Always use `--force-with-lease`.** Never `--force` on a shared branch that
others may have pulled or pushed. If the lease check trips, that's the branch
being rewritten under someone — stop and re-sync, don't force past it.

## Interactive rebase to clean up

```bash
git rebase -i HEAD~5          # opens the todo list
```

In the editor, per line, change the keyword:

- `pick` — keep as-is.
- `reword` — keep the change but edit the message: `reword` the subject.
- `squash` — fold this commit into the **previous** one, prompting for a combined message.
- `fixup` — fold into the previous one **discarding this commit's message** (best for "oops" fixes; no prompt clutter).
- `drop` — delete the commit.

```text
pick  a1b2c3 feat: add parser
fixup d4e5f6 fix typo in parser     # folds into a1b2c3, message discarded
reword 78e901 chore: rename util     # keep change, edit message
```

After saving, resolve any conflicts with `git rebase --continue`, or abort with
`git rebase --abort` to return to the pre-rebase state.

## Reflog recovery (the undo you forgot you had)

`git reflog` lists **every** HEAD movement, including ones `git log` no longer
shows (resets, rebases, branch deletions). It's your safety net:

```bash
git reflog
# 5a4b3c2 HEAD@{0}: reset: moving to 5a4b3c2
# 9c8d7e6 HEAD@{1}: commit: feat: add thing   <- where you were before

git reset --hard 9c8d7e6       # restore the state from HEAD@{1}
```

Rule: `git reset --hard` is only safe when you can *name the state you're
leaving* from the reflog first. A vanished branch is recoverable too:

```bash
git branch recovered 9c8d7e6   # resurrect a "deleted" branch from its last SHA
```

Uncommitted work is the one thing reflog does **not** cover — `git stash` is
the checkpoint there (see Pitfalls).

## Which strategy when

| Situation | Strategy | Why |
|-----------|----------|-----|
| Solo feature branch | **Rebase** onto main, then merge/rebase to main | Linear history; no merge noise |
| Shared long-lived branch (team) | **Merge** main in / PR merge | Never rewrite commits others may have pulled |
| Many trivial/chained "wip" commits | **Squash** (interactive rebase) | Reviewable single commit per logical change |
| Hotfix onto production | Cherry-pick or short branch merge | Minimal diff, isolated |
| Preserve exact topology (release) | `--no-ff` merge | Keep the feature branch's existence visible |

Rule of thumb: **rewrite history only on branches only you own**; merge (don't
rebase) on anything shared.

## Guardrails

- Never `git push --force` on a shared branch others may have pulled — always `--force-with-lease`.
- Never `git reset --hard` without a stash or a reflog line you can recover to.
- Never rebase a branch already merged upstream — it re-creates duplicate commits (see Pitfalls).
- Commit messages: imperative mood, `type: subject`, avoid `&` and unbalanced quotes (tool-parsed output).

## Pitfalls

- **Rebasing an already-merged branch** replays its commits as fresh ones on
  main → duplicate commits. Check `git log origin/main..feat` is non-empty
  *before* rebasing, or compare `git merge-base`.
- **Long-lived branches drift**: rebase frequently (every fetch), not just
  before merge — a once-a-day rebase yields trivial conflicts; a two-week one
  yields pain.
- **Stash does not expire via reflog**: lost-for-now stashes need
  `git fsck --lost-found` as a last resort — but `git stash list` + a deliberate
  `git stash push` message (`git stash push -m "wip: parser"`) beats relying on that.
- **`git pull` default merge surprises**: on a shared branch a plain `git pull`
  creates a merge commit; use `git pull --rebase` when you want linear history.
- **Force-pushing after rebase while others pulled**: the lease will (correctly)
  block you; that is a signal to coordinate, not to pass `--force`.

## Checklist

- [ ] Branch cut from a freshly-fetched main.
- [ ] Commit messages: imperative, `type: subject`, no `&`, balanced quotes.
- [ ] Rebasing solo branch with `--force-with-lease`, not `--force`.
- [ ] Interactive rebase used for squash/fixup/reword before review.
- [ ] No rewrite of commits already pushed to a shared branch.
- [ ] Reflog understood as the recovery path before any `reset --hard`.