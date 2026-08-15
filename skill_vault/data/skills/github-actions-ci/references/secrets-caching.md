# Secrets & Caching Best Practices

## Secrets management

Never put secrets in workflow YAML. Reference them:

```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
steps:
  - run: pytest
    env:
      API_KEY: ${{ secrets.API_KEY }}
```

### Rules
- Add secrets under **Repo Settings → Secrets and variables → Actions**
- Use **fine-grained PATs** or deploy keys — never broad personal tokens
- GitHub auto-redacts secret values from logs, but **only if the value is intact**
- Partial/transformed secrets may leak — don't echo or manipulate them
- For PRs from forks, secrets are NOT available (security) — use `pull_request_target` sparingly

## Caching strategies

### pip cache (built-in, preferred)
```yaml
- uses: actions/setup-python@v5
  with:
    cache: "pip"
```
Caches `~/.cache/pip` keyed by your lockfile hash — zero config, just works.

### Custom cache
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pre-commit
    key: ${{ runner.os }}-pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}
```

### When to cache
- ✅ `~/.cache/pip` — large, stable, big win
- ✅ Downloaded models (HuggingFace cache) — if stable across runs
- ✅ `pre-commit` environments — speed up lint gate
- ❌ Build artifacts that change every run
- ❌ Large files that exceed GitHub's 10 GB cache limit per repo

## Branch protection

After CI is passing, protect your main branch:
- **Settings → Branches → Add rule → `main`**
- Check: "Require status checks to pass before merging"
- Search for `gate` (or individual job names) as required checks
- Check: "Require branches to be up to date before merging"