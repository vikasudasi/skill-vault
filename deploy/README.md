# Systemd deployment

These unit files run Skill Vault as two managed processes:

- `skillvault-mcp.service` (MCP streamable-http endpoint, `POST /mcp`)
- `skillvault-web.service` (homepage + dashboard + health endpoint)

Both processes must use the same `SKILL_VAULT_DB_PATH` on persistent storage.

## Install

1. Copy the repo to your host (example path: `/opt/skill-vault`) and install it:

   ```bash
   cd /opt/skill-vault
   make install
   ```

2. Copy units into systemd:

   ```bash
   sudo cp deploy/skillvault-mcp.service /etc/systemd/system/
   sudo cp deploy/skillvault-web.service /etc/systemd/system/
   ```

3. Create `/etc/skillvault.env` with your deployment settings (minimum example):

   ```bash
   SKILL_VAULT_DB_PATH=/var/lib/skill-vault/skill_vault.db
   SKILL_VAULT_MCP_HOST=0.0.0.0
   SKILL_VAULT_MCP_PORT=8000
   SKILL_VAULT_WEB_HOST=0.0.0.0
   SKILL_VAULT_WEB_PORT=8080
   SKILL_VAULT_ADMIN_USERNAME=admin
   SKILL_VAULT_ADMIN_PASSWORD=replace-with-strong-secret
   SKILL_VAULT_SEED_DIR=/var/lib/skill-vault/skills
   ```

4. Reload and start services:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now skillvault-mcp.service
   sudo systemctl enable --now skillvault-web.service
   ```

5. Verify:

   ```bash
   curl -fsS http://127.0.0.1:8080/healthz
   ```

## Public endpoint note

Expose the web and MCP services through your host firewall/proxy policy as desired.
When public, clients should use:

- MCP endpoint: `http(s)://<skill-vault-public>/mcp`
- Dashboard: `http(s)://<skill-vault-public>/dashboard`
