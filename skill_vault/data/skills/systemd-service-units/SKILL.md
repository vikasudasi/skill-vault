---
name: systemd-service-units
description: Run long-lived services under systemd — unit files, hardening, environment, logging, and auto-restart.
tags: [systemd, linux, service, devops, process-management]
triggers: [systemd, systemctl, service unit, daemon, auto-restart]
complexity: medium
time_estimate: 20-40 min
prerequisites: [linux, systemd]
source: Skill Vault curated library
verify: true
---

# Running Services with systemd

Use when a self-hosted process must start on boot and auto-restart on crash.

## Unit file

```ini
[Unit]
Description=Skill Vault MCP server
After=network.target

[Service]
Type=simple
User=svc
WorkingDirectory=/opt/skill-vault
ExecStart=/opt/skill-vault/.venv/bin/skill-vault serve --transport streamable-http --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3
EnvironmentFile=/etc/skill-vault/svc.env

[Install]
WantedBy=multi-user.target
```

## Manage it

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now skill-vault-mcp
sudo systemctl status skill-vault-mcp
sudo journalctl -u skill-vault-mcp -f
```

## Key options

- `Restart=on-failure` + `RestartSec` — crash recovery without a watchdog.
- `EnvironmentFile=` — keep secrets in a mode-0600 env file, not the unit.
- `User=`/`Group=` — run as an unprivileged user; **never run daemons as root**.
- `Type=simple` is right for a foreground process; `Type=notify`/`Type=forking`
  for daemons that signal readiness.

## Pitfalls

- After editing a unit you MUST `systemctl daemon-reload` or changes are ignored.
- If systemd is degraded/broken on the host, ship a no-systemd fallback (a plain
  run script) too — don't depend on systemd being healthy.
- A service that exits immediately with `Restart=on-failure` will still be
  retried; check `journalctl` for the real error.
