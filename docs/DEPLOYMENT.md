# Deployment & Self-hosting

Skill Vault runs as two processes that share one persistent data path.

## Architecture

```text
                    +---------------------------+
                    |      Reverse Proxy        |
                    | (Caddy/nginx/Traefik/TLS)|
                    +-------------+-------------+
                                  |
                 +----------------+----------------+
                 |                                 |
       https://host/mcp                     https://host/
                 |                                 |
        +--------v---------+              +--------v---------+
        | MCP Process      |              | Web Process      |
        | skill-vault serve|              | skill-vault web  |
        | streamable-http  |              | FastAPI/uvicorn  |
        +--------+---------+              +--------+---------+
                 |                                 |
                 +---------------+-----------------+
                                 |
                         +-------v--------+
                         | /data volume   |
                         | skill_vault.db |
                         | *.sqlite_vec*  |
                         +----------------+
```

## Quickstart from source

1. Install:

   ```bash
   make install
   ```

2. Initialize (first run):

   ```bash
   .venv/bin/skill-vault init
   ```

3. Local MCP for one agent process (stdio):

   ```bash
   .venv/bin/skill-vault serve
   ```

4. Public instance on host machine (two processes):

   ```bash
   .venv/bin/skill-vault serve --transport streamable-http
   .venv/bin/skill-vault web
   ```

5. Verify health:

   ```bash
   curl -fsS http://127.0.0.1:8080/healthz
   ```

### One-command public launcher (no systemd)

```bash
./scripts/run-public.sh
```

This starts migrations, launches MCP + web in the background, writes PID/log files under `run/`,
waits for `/healthz`, and stops both processes on exit.

## Docker quickstart

Both services in compose share the same named volume and the same `SKILL_VAULT_DB_PATH`.

```bash
docker compose up --build
```

Default endpoints:

- MCP streamable-http: `http://localhost:8000/mcp`
- Homepage/dashboard: `http://localhost:8080/` and `http://localhost:8080/dashboard`

## First-run onboarding

1. Create an agent key:
   - Dashboard flow: `http://<host>:8080/dashboard/onboard`
   - CLI flow:

     ```bash
     .venv/bin/skill-vault onboard --name "my-agent"
     ```

2. Seed skills (implemented in a later task, but this is the workflow path):

   ```bash
   .venv/bin/skill-vault seed
   .venv/bin/skill-vault reindex
   ```

3. Point your MCP client at:
   - stdio: `skill-vault serve`
   - streamable-http: `http(s)://<host>/mcp`

## Ports

- MCP transport (`skill-vault serve --transport streamable-http`): default `8000`
- Web app (`skill-vault web`): default `8080`

Override with env vars:

- `SKILL_VAULT_MCP_PORT`
- `SKILL_VAULT_WEB_PORT`

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SKILL_VAULT_DB_PATH` | `./skill_vault.db` | Primary SQLite database path. |
| `SKILL_VAULT_VECTOR_BACKEND` | `sqlite_vec` | Vector backend (`sqlite_vec` or `pgvector`). |
| `SKILL_VAULT_EMBED_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model id for embeddings. |
| `SKILL_VAULT_TRUST_ALLOW` | `verified,user` | Comma-separated trust tiers allowed in responses. |
| `SKILL_VAULT_CURATOR_KEY` | unset | Curator ed25519 private key (base64) for verified signing. |
| `SKILL_VAULT_MCP_HOST` | `0.0.0.0` | MCP bind host for streamable-http transport. |
| `SKILL_VAULT_MCP_PORT` | `8000` | MCP streamable-http bind port. |
| `SKILL_VAULT_WEB_HOST` | `0.0.0.0` | Web bind host. |
| `SKILL_VAULT_WEB_PORT` | `8080` | Web bind port. |
| `SKILL_VAULT_SEED_DIR` | `./skill_vault/data/skills` | Filesystem seed skills directory. |
| `SKILL_VAULT_PGVECTOR_DSN` | unset | Postgres DSN for `pgvector` backend. |
| `SKILL_VAULT_RATE_LIMIT_PER_MINUTE` | `60` | Per-key request ceiling for public endpoint. |
| `SKILL_VAULT_ADMIN_USERNAME` | `admin` | Dashboard superuser username. |
| `SKILL_VAULT_ADMIN_PASSWORD` | *(required — no default)* | Dashboard superuser password. Must be set (e.g. via `.env`); startup fails loudly if missing. |

## TLS and reverse proxy notes

Skill Vault does not terminate TLS itself — it binds plain HTTP and is designed to sit behind a reverse proxy that terminates TLS and forwards to it on localhost. The production deployment (`srv1838697.hstgr.cloud`) uses **nginx 1.30.4 + Let's Encrypt (certbot)**.

### As deployed (nginx + Let's Encrypt)

- **nginx** (from the official nginx.org stable repo — v1.30.4) terminates TLS on port `443` and redirects all HTTP on port `80` to HTTPS (except `/.well-known/acme-challenge/` for renewal).
- **Let's Encrypt** cert issued via HTTP-01 **webroot** challenge (`/var/lib/letsencrypt`), auto-renewed by `certbot.timer` (twice daily) with the `webroot` authenticator.
- **skill-vault binds `127.0.0.1` only** (`--host 127.0.0.1` for both `web` and `serve`). Only nginx is internet-facing. This keeps login + agent API keys off plain HTTP on the public interface.
- **Forwarding** (`/etc/nginx/conf.d/skillvault.conf`):
  - `location /` → `127.0.0.1:8080` (web/FastAPI)
  - `location /mcp` → `127.0.0.1:8100/mcp` (MCP streamable-http)
- **Must set** `X-Forwarded-Proto $scheme` so Skill Vault can detect it's behind TLS (otherwise redirects/HSTS can loop or emit `http` URLs).

### MCP-specific proxy requirements

For MCP streamable-http, forward:
- both `GET` and `POST`
- connection upgrade/SSE-related headers (`Upgrade`, `Connection`, etc.) — nginx needs a `map $http_upgrade $connection_upgrade { default upgrade; "" close; }` in its `http` block, plus `proxy_buffering off` and a generous `proxy_read_timeout` so SSE streams are not buffered.
- original `Host` header.

Public MCP URL under TLS is `https://<host>/mcp`. Minimum working nginx `location /mcp` block:

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:8100/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 300s;
    proxy_buffering off;
    client_max_body_size 16m;
}
```

### Other options

- Put both services behind Caddy/nginx/Traefik for TLS termination.
- Set request-size limits appropriately (`client_max_body_size` in nginx, equivalent elsewhere).

### Rebinding to localhost

To stop the app from being reachable directly on a public interface, bind both processes to `127.0.0.1`:

```bash
.venv/bin/skill-vault web  --host 127.0.0.1 --port 8080
.venv/bin/skill-vault serve --transport streamable-http --host 127.0.0.1 --port 8100
```

(Default is `0.0.0.0`; when running behind a proxy on the same host, always use `127.0.0.1`.)

## Persistence, backup, and restore

Persist `/data` (or your configured storage path). Skill Vault stores:

- SQLite metadata database (`skill_vault.db` by default)
- sqlite-vec sidecar file(s) (`*.sqlite_vec*`, same directory)

Backup command:

```bash
.venv/bin/skill-vault backup --out ./backups
```

Restore command (stop service first):

```bash
.venv/bin/skill-vault restore ./backups/skill-vault-<timestamp> --db-path ./skill_vault.db
```

Manual backup alternative:

1. Stop both `serve` and `web`.
2. Copy DB + sidecar vector files from the storage directory.
3. Restore files to the same paths.
4. Start services again.

## Managed public process options

- `systemd` units: `deploy/skillvault-mcp.service` and `deploy/skillvault-web.service`.
- No-systemd fallback script: `scripts/run-public.sh`.

## Upgrade runbook

1. Stop running services.
2. Pull latest source (or image).
3. Run migrations (`skill-vault migrate`) or allow startup auto-migrations.
4. Start MCP + web processes.
5. Verify:
   - `curl -fsS http://127.0.0.1:8080/healthz`
   - MCP smoke (for example, `search_skills` against `/mcp`).
