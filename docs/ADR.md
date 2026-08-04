# Skill Vault — Architecture Decision Records

Each ADR records a decision, its context, and the trade-offs considered. ADRs are append-only;
when a decision changes, add a new ADR superseding the old one rather than editing history.

---

## ADR-001 — Vector store & embeddings: SQLite + local all-MiniLM-L6-v2 (chosen)

**Status:** Accepted (2026-08-04) · **Supersedes:** none

### Context
`search_skills` needs ranked semantic retrieval over skill discovery metadata. `skills-mcp` runs
Qdrant (384-d) on a Cloudflare Worker. Skill Vault's thesis is **self-hosting + trust**, so we must
weigh a fully-managed third-party vector DB + edge runtime against a local, private equivalent.

### Decision
- Default backend: **SQLite + sqlite-vec** (SQLite-native vector search, 384-d), local embeddings
  via **sentence-transformers all-MiniLM-L6-v2**.
- The search layer lives behind a `VectorIndex` interface so a **pgvector** backend can be dropped
  in later for team/enterprise scale without touching tool code.

### Consequences
- **Pro:** fully private (no skill metadata leaves the host), zero ops, free, satisfies
  self-host + verified-supply-chain positioning; fast for hundreds–thousands of skills.
- **Con:** no multi-node scale-out or edge CDN (irrelevant at target scale); relies on a compiled
  sqlite-vec extension (bundle/pin for reproducibility).

### Trade-off vs skills-mcp
skills-mcp optimizes for a shared, host-anywhere public library (managed Qdrant + Cloudflare).
We optimize for self-sovereignty — consistent with the product's trust/supply-chain differentiator.

---

## ADR-002 — Skill retrieval: skill-as-data (return SKILL.md content), not dynamic tool registration

**Status:** Accepted (2026-08-04) · **Supersedes:** none

### Context
How should a retrieved skill become actionable in a consumer agent? Two options: (a) dynamically
register skill tools into the agent's toolset, or (b) return the SKILL.md content (instructions +
scripts) the agent reads and follows.

### Decision
Return **SKILL.md content as data** (`get_skill` returns the body + metadata). The consumer agent
reads and follows it. Dynamic tool registration is **not** a primary path.

### Consequences
- Low coupling, works with any MCP-compatible agent, minimal injection surface.
- A skill is just verifiable content — which is exactly what the trust layer (hash + signature)
  can protect. Dynamic registration would spread trust/integrity concerns across the runtime.

---

## ADR-003 — Per-agent identity & private vaults, not a single shared library

**Status:** Accepted (2026-08-04) · **Supersedes:** none

### Context
`skills-mcp` is one shared public library with zero auth/personalization. Our gap analysis showed
the open row is **per-agent identity**: agents push their own capabilities and pull them back,
scoped by an API key, alongside a curated global store.

### Decision
Every agent onboards to an identity and gets an API key (hash-at-rest). Skills carry a
`visibility` of `global` (read by all) or `personal` (owner-only). Auth enforces scope at the
tool layer; the semantic index filters by scope at query time.

### Consequences
- Enables "personal skill vaults" and push/pull of personal learnings — the product's core
  differentiator over skills-mcp.
- Imposes an auth requirement on `personal`/`all` scopes (see Auth task).

---

## ADR-004 — Trust layer is core OSS but must stay licensable (future open-core tier)

**Status:** Accepted (2026-08-04) · **Supersedes:** none

### Context
Monetization discussion (project timeline) recommends leading with an open-core enterprise
governance tier; the OSS core must stay fully free. The trust/supply-chain layer is both our
differentiator and the natural paid-tier surface.

### Decision
Implement content-hash pinning + ed25519 signatures + trust tiers (`verified|user|public`) as
**core OSS** — but keep the trust scope/crypto generic and policy-driven (configurable allow-lists,
pluggable signer/verifier) so org-governance features (RBAC, audit, policy) can be layered on as a
separate licensable surface without rearchitecting or re-licensing the core.

### Consequences
- No rework when the paid tier lands; the core remains Apache-2.0-friendly.
- Slight abstraction cost (policy hooks, pluggable verification) accepted for future-proofing.

---

## ADR-005 — Transports: stdio (local) + streamable-HTTP/SSE (remote), single FastMCP app

**Status:** Accepted (2026-08-04) · **Supersedes:** none

### Context
Agents integrate MCP in two ways: local (stdio, per-machine) and remote (a URL the agent reaches
over HTTP). The homepage/configure page must document both.

### Decision
A single FastMCP app implements all tools (transport-agnostic). It runs via stdio for local
clients and is mounted into the FastAPI app over streamable-HTTP/SSE for remote clients. Auth is
injected at the transport layer for HTTP; local clients supply the key via config.

### Consequences
- One tool implementation, two transports — no logic duplication.
- Remote access requires TLS/reverse-proxy (noted in Deployment runbook).
