# Changelog

All notable changes to Skill Vault are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-05

Initial public release of the self-hostable, semantic skill registry for AI agents.

### Added

- **Core MCP registry** (FastMCP) — 7 tools: `search_skills`, `get_skill`, `publish_skill`,
  `update_skill`, `delete_skill`, `list_my_skills`, `list_global_skills`, with stable
  `SV_*` error codes.
- **Semantic search** — local `all-MiniLM-L6-v2` embeddings (384-d) over skill metadata;
  cosine-similarity ranking; `sqlite-vec` default backend with a `pgvector` drop-in interface.
- **Per-agent auth** — API keys issued once at onboarding, stored sha256-hashed; `global` /
  `personal` / owner-only scope enforcement at the tool layer; per-key rate limiting.
- **Trust & supply-chain layer** — sha256 content hashing (integrity pin) + ed25519 signatures;
  trust tiers `verified` / `user` / `public`; configurable serving allow-list.
- **Versioned, immutable skills** — forward-only, content-addressed version history.
- **Web surface** (FastAPI) — homepage, `/configure` MCP guide, `/browse`, skill detail pages,
  dashboard with agent onboarding, skill CRUD, key rotation/revocation.
- **CLI** (`skill-vault`) — `init`, `migrate`, `onboard`, `whoami`, `seed`, `reindex`,
  `verify`, `curator gen-key`, `serve`, `web`, `backup`, `restore`.
- **Seed library** — 17 curated SKILL.md skills across core-dev, frameworks, cloud/infra, and
  AI/LLM, including one `verified` signed skill (`python-cli-typer`).
- **Deployment** — two-process architecture (MCP `:8000/mcp` + web `:8080`), Docker +
  Compose, systemd units, no-systemd `scripts/run-public.sh`, snapshot backup/restore.
- **Test suite + CI** — 111 hermetic tests, ~89% coverage, `ruff` + `ruff format --check` +
  `mypy` + `pytest --cov-fail-under=85` in GitHub Actions.

### Changed

- None (initial release).

### Fixed

- **SQLite cross-thread concurrency** — write transactions now serialize through a process-wide
  lock *and* each thread uses its own connection, eliminating a CPython sqlite3
  cursor-finalization race (`SystemError: commit ... returned NULL`) under concurrent publish.

### Security

- API keys hashed at rest; content integrity enforced on retrieval; optional curator
  verification; scope isolation between agents. See [SECURITY.md](SECURITY.md).

[0.1.0]: https://github.com/vikasudasi/skill-vault/releases/tag/v0.1.0
