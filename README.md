# Skill Vault

A self-hostable **MCP server** that is a semantic, on-demand **skill/capability registry** for AI
agents. Plug in **one** MCP endpoint; your agent retrieves exactly the skills it needs on demand —
no more dragging around thousands of local skill files (~50 tokens of context each, which explodes
past ~10k skills).

> **Status:** Foundation (docs + scaffold). Full README ships at release — see
> [docs/SPEC.md](docs/SPEC.md) for the authoritative architecture, data model, and MCP contract.

## Highlights

- **One MCP endpoint** — `search_skills` → lightweight cards → `get_skill` for the full body on demand.
- **Per-agent identity & private vaults** — push personal learnings, pull them back later, scoped by API key.
- **Verified supply chain** — content-hash pinning, optional ed25519 signatures, trust tiers (`verified | user | public`).

## Getting started (scaffold)

```bash
make init      # create SQLite schema
make migrate   # apply forward-only migrations
skill-vault --help
```

_Interactive quickstart, config, and deployment docs land with the implementation milestones._

## Layout

- `docs/SPEC.md` — architecture, data model, MCP contract (source of truth)
- `docs/ADR.md` — architecture decision records
- `migrations/` — forward-only SQL migrations
- `skill_vault/` — Python package (config, db, models, MCP tools, search, web)

## License

Apache-2.0 (pending at release).
