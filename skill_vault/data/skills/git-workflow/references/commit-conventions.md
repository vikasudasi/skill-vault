# Commit Message Conventions

## Conventional Commits format

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

## Common types

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes nor adds |
| `test` | Adding/updating tests |
| `chore` | Build, CI, tooling |
| `perf` | Performance improvement |

## Rules

- **Imperative mood:** "add feature" not "added feature"
- **Lowercase subject:** `feat: add login` not `Feat: Add login`
- **No period at end of subject**
- **Keep subject under 72 chars**

## Examples

```
feat(auth): add OAuth2 login flow
fix(db): prevent connection leak on timeout
docs: update API reference for v2 endpoints
refactor(cache): extract TTL logic to separate module
chore(deps): bump requests to 2.32.0
```

## Recovery commands

```bash
# See what you did and undo
git reflog

# Uncommit but keep changes
git reset --soft HEAD~1

# Discard last commit entirely
git reset --hard HEAD~1

# Recover lost commits
git fsck --lost-found
```