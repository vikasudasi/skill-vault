# Contributing to Skill Vault

Thanks for your interest in contributing! Skill Vault is a self-hostable, semantic skill
registry for AI agents. All contributions — code, docs, skills, bug reports — are welcome.

## Code of conduct

Be respectful and constructive. This project has a small maintainer bus; treat every
contribution as if it will be reviewed by someone who wasn't there when you wrote it.

## Before you start

- **Open an issue** for any behaviour change or non-trivial feature before writing code, so we
  can agree on direction.
- Keep PRs **small and focused** — one logical change per PR is much easier to review.
- For questions and feature ideas, open a discussion rather than a PR.

## Project layout (short)

```
skill_vault/            # python package
  ├── server.py         # MCP server (FastMCP) — tool surface
  ├── tools.py          # MCP tool implementations
  ├── service.py        # RegistryService — domain logic + write transactions
  ├── search.py         # embeddings + vector index (sqlite-vec / pgvector)
  ├── auth.py           # API-key issue / verify / scope
  ├── trust.py          # sha256 hash + ed25519 signatures + tiers
  ├── seed.py           # curated-library ingest (seed command)
  ├── web/              # FastAPI: homepage, dashboard, /configure
  └── cli.py            # `skill-vault` CLI
migrations/             # forward-only SQL migrations
skill_vault/data/skills/ # curated SKILL.md seed library
tests/                  # hermetic tests (temp DB, fake embedder/store)
docs/                   # SPEC, ADR, DEPLOYMENT
```

## Development setup

```bash
git clone https://github.com/vikasudasi/skill-vault.git
cd skill-vault
make install
. .venv/bin/activate
```

## Skill authoring

To add a curated skill, create a directory under `skill_vault/data/skills/<name>/` with a
`SKILL.md` file:

```markdown
---
name: your-skill
description: one-line summary used for search cards
tags: [python, cli]
triggers: [cli, argparse]
complexity: low
time_estimate: 10 min
prerequisites: [python 3.11]
source: Skill Vault curated library
---
# Body — the actual runbook/instructions the agent will follow
```

- `name` and `description` are required; `tags`/`triggers` improve semantic recall.
- To mark a skill for curator signing, set `verify: true` in its frontmatter.
- Run `.venv/bin/skill-vault seed --curator-key <key>` to ingest (see Trust docs).

## Quality gates (must pass before submitting)

```bash
make check          # ruff lint + ruff format --check + mypy
pytest tests/ --cov=skill_vault --cov-fail-under=85
```

- Python ≥ 3.11, `from __future__ import annotations`, type hints throughout.
- Follow the project conventions (dataclasses with `slots=True`, `ruff` line length 100).
- Tests must be **hermetic**: temp DB, fake embedder/store — no network, no model download.

## Test conventions

- `tests/conftest.py` provides `db`, `fake_embedder`, `fake_store`, and helper inserters.
- New features should come with focused tests covering happy path + edge cases.
- Keep coverage ≥ 85% (the CI gate).

## Commit & PR

- Write clear, imperative commit messages ("Add X", "Fix Y").
- Keep the tree clean before and after (`git status`).
- In your PR description: what changed, why, and how you verified it.

## Release process (maintainers)

Releases are tagged `v<semver>` with a CHANGELOG entry. The `main` branch must be green
(`make check` + full test suite) before tagging. See [SECURITY.md](SECURITY.md) for
vulnerability disclosure.
