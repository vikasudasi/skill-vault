---
name: security-secrets-management
description: Keep secrets out of git, scan for leaks, use least-privilege keys, harden a self-hosted service, and validate supply-chain trust.
tags: [security, secrets, gitignore, gitleaks, tls, passwords, supply-chain, devops]
triggers: [secrets, api key, .env, gitleaks, leak, tls, hash password, supply chain, signed]
complexity: medium
time_estimate: 45-90 min
prerequisites: [git, python]
source: Skill Vault curated library
verify: true
---

# Secrets, Service Hardening, and Supply-Chain Trust

Use when standing up a self-hosted service, wiring API keys, or shipping code to
the public — anywhere a leaked credential or unsigned artifact is a real cost.

## 1. Never commit secrets

- Keep secrets in an untracked `.env` (gitignored), read them at runtime via env
  vars, never in source.
- `.gitignore` must include `.env`, `*.pem`, `*.key`, keystores, and local config.
- If a secret was ever committed, assume it's compromised: **rotate it**, don't
  just delete it. History preserves it.

> Skills like Skill Vault's `security-secrets-management` and its sibling
> `deploy-secret-hygiene` exist precisely because "remove the line" is a false fix.

## 2. Scan for leaks continuously

| tool    | finds                            | run                        |
|---------|----------------------------------|----------------------------|
| gitleaks | known secret patterns + entropy | pre-commit + CI            |
| bandit  | Python code security smells     | `bandit -r .`              |
| git history scan | secrets already committed | `gitleaks detect --log-opts="--all"` |

Gate CI on a clean scan; the cost of a leak multiplies the moment it's public.

## 3. Least-privilege API keys

- Scope each key to the minimum capability it needs (read-only, one bucket, one
  API) and give it a short expiry.
- Name keys so you can identify and revoke them (`sv-ci-deploy`, not `key1`).
- Rotate on a schedule and on any suspicion.
- Prefer a signed/token identity over raw long-lived keys where your platform
  supports it — this mirrors Skill Vault's trust model below.

## 4. SSH key hygiene

- Use a passphrase-protected key or an agent; never a shared key in a repo.
- Add public keys to the target via `ssh-copy-id`, and restrict keys in
  `authorized_keys` with `command=`/`no-port-forwarding` where the key is purpose-built.
- Fingerprint-check on first connect; reject a changed host key.

## 5. Hardening a self-hosted service

- **TLS**: terminate HTTPS at the edge (nginx with Let's Encrypt); redirect all
  HTTP to HTTPS and set HSTS. A self-hosted app behind nginx should see only
  `X-Forwarded-Proto: https` and treat non-TLS requests as untrusted.
- **Passwords**: hash with a slow adaptive KDF — `pbkdf2_hmac` (many iterations)
  or `argon2`. Never store plaintext, single-round SHA, or MD5.
  ```python
  import hashlib

  salt = secrets.token_bytes(16)
  digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600_000)
  ```
  Compare with `hmac.compare_digest` — not `==` — to avoid timing side channels.
- **Sessions**: use `httpOnly` cookies (`Set-Cookie: ...; HttpOnly; Secure;
  SameSite=Lax`) so JS can't read the token and it isn't sent over plain HTTP.

## 6. Supply-chain trust: verify what you run

The practical baseline is pinned, hashed dependencies and reproducible installs.
Skill Vault's own design is the stronger model: every curated skill carries a
cryptographic signature recorded in the `trust` table with `signed_by`,
`public_key` (drawn from a `known_public_keys` allowlist), and a `verified` tier
that is only reached when the signature genuinely verifies against a known key.
Anything unsigned or from an unknown key stays at lower trust. The throughput is:
*trust is the identity + signature, never the source URL alone.* Apply the same
principle to your toolchain: pin by hash, and deny installs that don't match.

## Pitfalls

- Committing `.env` is the classic; a pre-commit hook running gitleaks stops it.
- A leaked secret that "wasn't used in production" is still public — rotate it.
- Short salts, low KDF iterations, and `==` password comparison all weaken hashes.
- `httpOnly` only helps if it's also `Secure` and `SameSite`; a bare cookie leaks.
- Treating the source URL as proof of provenance — verify the signature/key.
- Rebroadcasting secrets in READMEs, error messages, or logs undoes all hygiene.

## Verify / Checklist

- [ ] `.gitignore` untracks `.env`/keys; `git status` is clean of secrets
- [ ] gitleaks + bandit scan clean in CI and locally
- [ ] API keys are scoped, named, expiring, and rotatable
- [ ] nginx terminates TLS; HTTP redirects to HTTPS; HSTS set
- [ ] Passwords hashed with pbkdf2/argon2 and compared via `compare_digest`
- [ ] Cookies are `HttpOnly; Secure; SameSite`
- [ ] Verify signatures/allowed keys before trusting external dependencies