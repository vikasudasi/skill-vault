---
name: github-actions-ci
description: Structure GitHub Actions workflows — jobs, steps, caching, matrix builds, secrets, and a quality gate that blocks merges.
tags: [github, ci, github-actions, workflow, pipeline, devops]
triggers: [github actions, ci, workflow, pipeline, quality gate, ci badge]
complexity: medium
time_estimate: 30-60 min
prerequisites: [git, github]
source: Skill Vault curated library
verify: true
---

# GitHub Actions Continuous Integration

Use when wiring a repo so every push/PR runs lint, type-check, format-check, and
tests — and blocks merge when they fail. This is exactly what Skill Vault's own
CI does: `test`, `ruff check`, `mypy`, and `ruff format --check` running as a
pre-merge gate.

## Anatomy

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - run: pip install -e ".[dev]"
      - run: pytest
```

- `on` defines triggers: push to main, every PR, `schedule` for cron.
- Each `job` runs on its own fresh runner — share nothing between jobs; combine
  steps that need the same environment.

## Checkout + setup-python caching

`actions/checkout@v4` fetches the repo. `setup-python` with `cache: "pip"` caches
the pip download cache/Ci keyed to your lockfile, cutting install time. Pin
action versions by tag (`@v4`) or, for supply-chain rigor, by SHA.

## The quality gate

Structure the gate so a single failed check blocks merge (protect the branch with
"Require status checks to pass before merging"):

| step           | command                          | failure meaning              |
|----------------|----------------------------------|------------------------------|
| lint           | `ruff check .`                   | style/import errors          |
| typecheck      | `mypy skill_vault`               | type errors                  |
| format-check   | `ruff format --check .`          | not formatted                |
| test           | `pytest`                         | behaviour broken             |

Keep the gate fast — it runs on every commit. Run `test` as its own job so it can
cache longer and fail independently. Add a coverage threshold (`pytest-cov
--cov-fail-under=85`) so regressions also block.

## Caching dependencies

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('pyproject.toml') }}
```

Simpler: rely on `setup-python`'s `cache: "pip"`. Only hand-roll a cache when you
have a non-pip artifact (e.g. a downloaded model).

## Matrix builds

```yaml
strategy:
  matrix:
    python-version: ["3.11", "3.12"]
```
Runs the job once per combination — good for testing across versions/OSes. Don't
matrix unless you actually support those versions; it multiplies cost and time.

## Secrets in CI

- Add secrets under repo Settings → Secrets; reference as
  `${{ secrets.MY_SECRET }}` in an `env:` block or `with:`.
- Never put secrets in the YAML or echo them to logs — GitHub redacts but only if
  the value is intact; a partial/transformed secret may leak.
- Prefer scoped, short-lived tokens (a deploy key / fine-grained PAT) over a
  broad personal token.

## Pitfalls

- A single giant job is brittle: one failed step aborts-dependent steps. Split
  independent checks into separate jobs.
- Forgetting `cache: "pip"` makes every run reinstall everything — slow and flaky.
- Pinning nothing (bare `actions/checkout`) risks supply-chain drift; pin tags.
- Format-check and lint failing *after* tests is misleading — run the cheap
  static checks first so failures surface early.
- `on:` defaults to nothing; if you forget it the workflow never runs.

## Verify / Checklist

- [ ] Workflow runs on push and every PR, and respects `on:` correctly
- [ ] `setup-python` cache is on; deps install deterministically
- [ ] Gate runs lint → typecheck → format-check → test so failures surface early
- [ ] Branch protection requires the status checks before merge
- [ ] No secrets in the YAML or logs; scoped tokens only
