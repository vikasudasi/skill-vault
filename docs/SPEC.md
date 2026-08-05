# Skill Vault — Technical Specification (SPEC)

> Version: 1.0.0 · Status: **Foundation** · Owner: Vik Udasi / Hermes

Self-hostable MCP server that acts as a semantic, on-demand **skill/capability registry** for AI agents.
An agent wires in exactly **one** MCP endpoint and retrieves relevant skills on demand instead of
maintaining thousands of local skill files (which blow up context). Differentiates from
`skills-mcp` (shared free library, zero identity) and `agentregistry` (org catalog/governance only)
via **per-agent identity + private skill vaults + a verifiable trust/supply-chain layer.**

This document is the single source of truth for architecture, the data model, and the MCP contract.
All subsequent implementation tasks (Core MCP server, Semantic search, Auth, Trust layer, Web
dashboard, Homepage, Deployment, Tests, Seed, README) MUST conform to this spec.

---

## 1. Product Goal & Scope

**Problem.** An agent using progressive-disclosure skills pays ~50 tokens/skill of description in
context. At 1,000–10,000 skills the descriptions alone exceed the context window (≈500k tokens at
10k skills). Local skill files also don't sync across machines, teams, or agents.

**Solution.** One MCP endpoint. The agent calls `search_skills("schema migration for postgres")`
and gets back ranked, lightweight skill *cards* (name + one-line description + trust) — then calls
`get_skill(id)` only for the full SKILL.md body of the one it wants. Skills are first-class,
versioned, content-addressed, and optionally signed. Every agent gets its own private vault plus
read access to a curated global store.

**Out of scope (for now):** enterprise org-governance features (SSO/RBAC/audit/compliance) —
deliberately deferred, they are the future paid (open-core) tier. Keep the trust layer **licensable**
so that tier can be layered on without rework (see Monetization decision, project timeline).

## 2. Tech Stack & Key Decisions

| Concern | Choice | Rationale |
|---|---|---|
| MCP server | **FastMCP** (Python) | First-class stdio + SSE/streamable-HTTP, tool schema auto-gen, wide agent support |
| Web layer | **FastAPI + uvicorn** | Hosts dashboard, homepage, /configure page, and mounts MCP transport for remote access |
| DB | **SQLite** (std) | Zero-ops self-host; WAL mode; single file; ideal for a personal/self-host registry |
| Vector store | **sqlite-vec** (extension) | SQLite-native vector search avoids an external service; perfect for self-host scale |
| Embeddings | **all-MiniLM-L6-v2** (384-d, sentence-transformers) | Same embedder as Vik's agent-knowledge-graph; local (no API cost), good-enough semantic recall |
| Optional scale-out | **pgvector** (SQLAlchemy backend) | Port for teams/enterprise; same interface, swappable |
| Auth keys | `secrets.token_urlsafe` + **sha256 hashing** at rest | Never store raw keys (see Auth task) |
| Trust crypto | **sha256** content hash + **ed25519** signatures | Deterministic integrity + cheap sign/verify (see Trust task) |
| Conventions | Python ≥3.11, `from __future__ import annotations`, `@dataclass(slots=True)`, type hints | Matches Vik's project conventions |

### ADR-001 — Vector store: SQLite + local embeddings (chosen) vs Qdrant/Cloudflare (skills-mcp)

**Context.** `skills-mcp` runs Qdrant (384-d) on a Cloudflare Worker — a fully *managed* vector DB +
edge runtime. That's great when you trust a third party and want scale-out, but Skill Vault's
differentiator is *self-hosting + trust*. Adding a managed Qdrant/Cloudflare dependency would (a)
send skill embeddings/content to a third party, (b) add ops burden, and (c) contradict the
self-host + verified-supply-chain story.

**Decision.** Use **SQLite + sqlite-vec** for the default backend and local `all-MiniLM-L6-v2`
embeddings. The search layer is defined behind a `VectorIndex` interface so a `pgvector` port is a
drop-in later. Justification vs skills-mcp: for the target scale (hundreds–thousands of skills,
single-tenant or small-team self-host), a local SQLite vector index is simpler, cheaper, fully
private, and has adequate recall. We trade max scale-out (Qdrant) and edge CDN (Cloudflare) for
self-sovereignty — which is the product thesis.

## 3. Repository Layout

```
skill-vault/
├── docs/
│   ├── SPEC.md                 # this file
│   ├── ADR.md                  # decision records (ADR-001 above, +)
│   ├── DEPLOYMENT.md           # (Deployment task)
│   └── api.md                  # generated/curated API reference
├── migrations/
│   └── 001_baseline.sql        # schema (agents, api_keys, skills, skill_versions, trust, tags)
├── skill_vault/
│   ├── __init__.py
│   ├── config.py               # env-based config (pydantic-settings or dataclass)
│   ├── db.py                   # sqlite connection, WAL, migrations runner
│   ├── models.py               # dataclasses/Pydantic models for skills, agents, trust
│   ├── schema.sql              # DDL (also embedded / mirrored in migrations)
│   ├── server.py               # MCP server (FastMCP) — tool surface + entrypoints
│   ├── tools.py                # MCP tool implementations (search/get/publish/update/list/...)
│   ├── search.py               # VectorIndex interface + SqliteVecIndex + Embedder
│   ├── auth.py                 # (Auth task) key issue/verify/scope
│   ├── trust.py                # (Trust task) content hash, signatures, tiers
│   ├── web/
│   │   ├── app.py              # FastAPI app, mounts MCP transport, / + /configure
│   │   ├── dashboard.py        # (Dashboard task)
│   │   └── static/…            # homepage / configure assets
│   ├── cli.py                  # `skill-vault` CLI: init, migrate, seed, serve
│   └── py.typed
├── tests/                      # (Test task) hermetic, temp DB, mocked embedder
├── skill_vault/data/skills/    # (Seed task) curated SKILL.md library
├── .env.example
├── pyproject.toml
├── Makefile
├── README.md                   # stub (full README in Release task)
└── LICENSE
```

## 4. Data Model (SQLite schema)

Conventions: UUID (v4) primary keys stored as TEXT; `created_at`/`updated_at` as
`TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))` (ISO-8601 UTC); FK
`ON DELETE CASCADE` where sensible. `PRAGMA journal_mode=WAL;` + `PRAGMA foreign_keys=ON;`.

### `agents`
Per-agent identity (an "agent" = one API key holder / assistant).

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID |
| name | TEXT NOT NULL | human label shown in dashboard |
| created_at | TEXT | ISO-8601 UTC |
| updated_at | TEXT | last modification |

### `api_keys`
Hash-only key storage. Raw key shown once at onboarding, never persisted.

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID |
| agent_id | TEXT NOT NULL FK→agents.id | owning agent |
| key_hash | TEXT NOT NULL UNIQUE | sha256 hex of the raw key |
| key_prefix | TEXT NOT NULL | first 8 chars, for display/rotation |
| created_at | TEXT | |
| last_used_at | TEXT NULL | updated on each authenticated call |
| revoked_at | TEXT NULL | non-null = revoked |

### `skills`
A logical skill; versioned content lives in `skill_versions`.

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID; stable across versions |
| name | TEXT NOT NULL | unique per owner scope |
| owner_agent_id | TEXT NULL FK→agents.id | NULL ⇒ global/seed skill; else personal vault skill |
| visibility | TEXT NOT NULL CHECK IN ('global','personal') | global readable by all; personal only by owner |
| current_version_id | TEXT NULL FK→skill_versions.id | points to latest released version |
| created_at | TEXT | |
| updated_at | TEXT | |

### `skill_versions`
Immutable, content-addressed versions of a SKILL.md.

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID |
| skill_id | TEXT NOT NULL FK→skills.id | |
| version | INTEGER NOT NULL | 1-based, monotonic per skill |
| content_hash | TEXT NOT NULL | sha256 of canonical serialization; integrity pin |
| name | TEXT NOT NULL | denormalized for search |
| description | TEXT NOT NULL | one-line, for search card + embedding |
| tags | TEXT NOT NULL | JSON array of strings (searchable) |
| triggers | TEXT NOT NULL | JSON array of trigger phrases |
| meta_json | TEXT NOT NULL | complexity, time_estimate, prerequisites, source |
| body | TEXT NOT NULL | full SKILL.md markdown body |
| created_at | TEXT | |
| UNIQUE(skill_id, version) | | |

### `trust`
Trust tier + signature record per skill version.

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID |
| skill_version_id | TEXT NOT NULL FK→skill_versions.id | one trust record per version |
| tier | TEXT NOT NULL CHECK IN ('verified','user','public') | verified=curator-signed; user=owner's own; public=community |
| signed_by | TEXT NULL | curator/verifier identity (pubkey id or name) |
| signature | TEXT NULL | ed25519 signature (base64) over content_hash |
| public_key | TEXT NULL | verifier ed25519 public key (base64) |
| verified_at | TEXT NULL | when verified |
| UNIQUE(skill_version_id) | | |

### `tags`
Normalized tags (optional; search can also read `skill_versions.tags` JSON). Kept for filtering.

| column | type |
|---|---|
| id | TEXT PK |
| name | TEXT NOT NULL UNIQUE |

### `skill_tags`
Join table `skill_version_id` ↔ `tag_id`.

## 5. MCP Tool Contract

Server name: `skill-vault`. Transport: **stdio** (local) and **streamable-HTTP/SSE** (remote, mounted
in FastAPI). Auth: agent API key passed via the MCP `authorization`/auth header (remote) or config
(local) — see Auth task for exact mechanics.

All tools return `{"ok": bool, ...data}` with MCP tool-result JSON. Errors use MCP error codes plus
stable custom codes:

| code | meaning |
|---|---|
| `SV_UNAUTHENTICATED` | missing/invalid agent key |
| `SV_FORBIDDEN` | key valid but lacks access (cross-agent private / policy) |
| `SV_NOT_FOUND` | skill/version not found |
| `SV_INVALID_SKILL` | malformed skill payload / missing required frontmatter |
| `SV_INTEGRITY` | content hash mismatch (tamper) |
| `SV_RATE_LIMITED` | key over quota |
| `SV_CONFLICT` | duplicate name in scope |

### `search_skills`
```python
def search_skills(
    query: str,               # natural-language search string
    scope: str = "global",    # "global" | "all" (global+own personal) | "personal"
    limit: int = 10,          # 1..50
    min_trust: str | None = None,  # filter: "verified" | "user" | "public"
    agent_key: str | None = None,  # required for "personal"/"all" scopes
) -> list[SkillCard]
```
`SkillCard = {id, name, description, tags, trust, score, version}` — **lightweight, no body.**
`trust` is the effective tier (highest of the version's records). `score` = similarity (0..1).

Scope semantics:
- `global` → any agent (even unauthenticated) may search the curated global store.
- `personal` → only that agent's private vault (**requires valid `agent_key`**).
- `all` → union of global + own personal (**requires `agent_key`**). Cross-agent private is never returned.

### `get_skill`
```python
def get_skill(id: str, agent_key: str | None = None) -> SkillDetail
```
`SkillDetail = {id, name, description, body, version, tags, trust, content_hash, verified, owner}`.
**Full body** returned. Integrity: server re-derives `sha256(body)` and verifies it matches
`content_hash` before returning; on mismatch raises `SV_INTEGRITY` (never returns tampered content).
Returns global skills to anyone; personal skills only to the owning `agent_key`.

### `publish_skill`
```python
def publish_skill(skill: SkillInput, visibility: str = "personal", agent_key: str) -> PublishResult
```
`SkillInput = {name, description, tags[], triggers[], body, meta{}}`. Creates a new skill; if a skill
with the same `name` exists in the requesting agent's scope, returns `SV_CONFLICT` (use
`update_skill`). Assigns `version = 1`, `content_hash = sha256(canonical(skill))`, `trust = 'user'`
(for personal) or `'public'` (for global, if publishing allowed).

### `update_skill`
```python
def update_skill(id: str, skill: SkillInput, agent_key: str) -> PublishResult
```
Only the owning agent (or curator for global seed) may update. Appends a **new immutable version**
(`version = max+1`), updates `current_version_id`. Previous versions remain addressable/hash-pinned.

### `list_my_skills`
```python
def list_my_skills(agent_key: str, scope: str = "all") -> list[SkillCard]
```
Lists cards (no bodies) for the authenticated agent's personal vault (and optionally global).

### `delete_skill`
```python
def delete_skill(id: str, agent_key: str) -> DeleteResult
```
Owner-only soft delete (marks removed) — keeps version history for audit (see Trust task).

### `verify_skill`
```python
def verify_skill(id: str) -> VerifyResult
```
Returns `{trust, verified: bool, signed_by, content_hash}` for a skill's current version. No key
needed; consumers call this (or read `trust` on get) to validate before executing a pulled skill.

## 6. Semantic Search Design

- **Embedder**: `all-MiniLM-L6-v2` (384-d), sentence-transformers. Deterministic, local.
- **Embedded text**: weighted concatenation of `name`, `description`, `tags`, `triggers`,
  and (optionally) lead section of `body` — i.e. discovery *metadata*, not the whole body
  (mirrors skills-mcp's "embed only frontmatter" insight; keeps indexes small).
- **Index**: `VectorIndex` interface → `SqliteVecIndex` (sqlite-vec, 384-d) default; `PgVectorIndex`
  optional. Stores per `skill_versions.id` + embedding.
- **Query flow**: embed query → cosine-similarity top-k → apply scope/trust/visibility filters →
  return cards sorted by score. Re-index happens on publish/update and via `cli reindex`
  (idempotent).
- **No hardcoded sources** (product rule): retrieval is purely semantic over whatever the registry
  holds — matching the "no pinned sources" principle used in Vik's news cron.

## 7. Web Surface (FastAPI)

- Public routes:
  - `GET /` homepage (marketing + product pitch + live endpoint banner + links to dashboard/configure/docs)
  - `GET /configure` MCP configuration guide with verified stdio + streamable-http commands/snippets
  - `GET /healthz` liveness
- Dashboard/admin area (HTTP Basic auth, credentials distinct from agent API keys):
  - `GET /dashboard` agents overview
  - `GET /dashboard/onboard` and `POST /dashboard/onboard` (creates agent + shows API key once)
  - `GET /agents/{agent_id}` agent dashboard (personal skills tab + global browser tab + key management)
  - `GET /agents/{agent_id}/skills/new`, `POST /agents/{agent_id}/skills`
  - `GET /agents/{agent_id}/skills/{skill_id}/edit`, `POST /agents/{agent_id}/skills/{skill_id}`
  - `POST /agents/{agent_id}/skills/{skill_id}/delete`
  - `POST /agents/{agent_id}/keys/{key_id}/rotate` (shows new key once)
  - `POST /agents/{agent_id}/keys/{key_id}/revoke`
- Public browse/read routes:
  - `GET /browse` global search + pagination
  - `GET /skills/{skill_id}` metadata + trust + integrity status (skill body not rendered)
- Configure-page auth note: `agent_key` is passed as a per-tool argument for private/global operations;
  no connection-level key header is required for Skill Vault tool authorization.
- MCP streamable-HTTP/SSE transport mounted for remote agent access (Core MCP + Deployment tasks).

## 8. Configuration (`.env.example` → `config.py`)

| var | default | notes |
|---|---|---|
| `SKILL_VAULT_DB_PATH` | `./skill_vault.db` | SQLite file |
| `SKILL_VAULT_VECTOR_BACKEND` | `sqlite_vec` | `sqlite_vec` \| `pgvector` |
| `SKILL_VAULT_EMBED_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers id |
| `SKILL_VAULT_TRUST_ALLOW` | `verified,user` | host policy allow-list (Trust task) |
| `SKILL_VAULT_CURATOR_KEY` | *(unset)* | ed25519 private key (base64) for signing (Trust task) |
| `SKILL_VAULT_WEB_HOST` / `_PORT` | `0.0.0.0` / `8000` | uvicorn bind |
| `SKILL_VAULT_ADMIN_USERNAME` | `admin` | dashboard basic-auth username (set securely in production) |
| `SKILL_VAULT_ADMIN_PASSWORD` | `skillvault` | dashboard basic-auth password (set securely in production) |
| `SKILL_VAULT_SEED_DIR` | `./skill_vault/data/skills` | curated seed library (Seed task) |

## 9. CLI

`skill-vault` subcommands: `init` (create schema), `migrate`, `seed`, `reindex`, `serve` (stdio or
`--http`), `agent create` (issue key, shown once). Implemented in `cli.py` with the project's CLI
conventions (rich tables, exit codes, `--help`).

## 10. Compliance & Consistency Rules

- Python ≥3.11, `from __future__ import annotations`, f-strings, `@dataclass(slots=True)`.
- `pyproject.toml` build-backend `setuptools.build_meta`; deps: `mcp[cli]`, `fastapi`, `uvicorn`,
  `sqlite-vec`, `sentence-transformers`, `pydantic-settings`, `click`, `rich`.
- Lint `ruff`, format `ruff format`, typecheck `mypy`, test `pytest` (≥85% cov) — CI gates (Test task).
- Migrations are forward-only, applied by the migration runner; `001_baseline.sql` ships here.
