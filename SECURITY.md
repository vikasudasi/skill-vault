# Security Policy

Skill Vault is a self-hostable skill registry with a **trust & supply-chain layer** at its
core. We take security seriously. This document describes supported versions and how to
responsibly report vulnerabilities.

## Supported versions

| Version | Supported |
|---|---|
| latest `main` | ✅ |
| current tagged release | ✅ |
| older releases | ❌ (upgrade) |

## Security model (short)

- **API keys** are stored as **sha256 hashes only** — raw keys are shown once at onboarding and
  never persisted. Rotate `sv_...` keys from the dashboard or CLI if compromised.
- **Content integrity** — every skill version is sha256 content-addressed; `get_skill`
  re-derives the hash and refuses to return tampered content (`SV_INTEGRITY`).
- **Signatures** — optional ed25519 signatures give a `verified` tier. Treat a skill as
  verified only when its signature validates against a public key you trust.
- **Access control** — `global` vs `personal` (owner-only) scope enforced at the tool layer;
  cross-agent private access is always rejected.
- **Rate limiting** on the public endpoint (`SKILL_VAULT_RATE_LIMIT_PER_MINUTE`).
- **Transport** — remote access is expected behind **TLS** (reverse proxy). Do not expose the
  plain HTTP endpoints to the public internet.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report privately:

- **GitHub private advisory (preferred):** open a security advisory on the repository at
  `https://github.com/vikasudasi/skill-vault/security/advisories/new`.
- **Email:** use a maintainer contact associated with the repository.

What to include:
1. Steps to reproduce (minimal, concrete).
2. Affected component and version.
3. Impact / what an attacker could do.
4. Suggested fix, if you have one.

## Disclosure policy

We aim to respond within **5 business days** of a report. We will work with you to confirm the
issue, prepare a fix, and coordinate disclosure. We practice **coordinated disclosure**: we ask
that you keep the issue private until a fix is released.

## Thanks

We appreciate the community helping keep Skill Vault trustworthy for everyone who self-hosts it.
