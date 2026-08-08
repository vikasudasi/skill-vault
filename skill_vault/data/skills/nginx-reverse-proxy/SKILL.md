---
name: nginx-reverse-proxy
description: Configure nginx as a reverse proxy with TLS termination, headers, and upstream health — for self-hosted web apps.
tags: [nginx, reverse-proxy, web, devops, linux, self-host]
triggers: [nginx, reverse proxy, proxy, tls, ssl termination]
complexity: medium
time_estimate: 30-60 min
prerequisites: [linux, nginx]
source: Skill Vault curated library
verify: true
---

# nginx as a Reverse Proxy

Use when exposing an internal web app on :80/:443 behind nginx on a self-hosted box.

## Basic server block

```nginx
server {
    listen 443 ssl;
    server_name skills.example.com;

    ssl_certificate     /etc/letsencrypt/live/skills.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/skills.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Key directives

- `proxy_set_header Host $host` — app sees the external host, not 127.0.0.1.
- `X-Forwarded-For`/`X-Forwarded-Proto` — needed by apps behind TLS for correct
  scheme detection and logging.
- Preserve websockets/SSE with `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade;`.

## TLS

- `certbot --nginx -d skills.example.com` for Let's Encrypt; it edits the block for you.
- After issuing, keep `synchronous NORMAL`-class settings; set a renewal hook.

## Pitfalls

- Only pass `proxy_set_header` lines the app actually needs; leaking internal
  IPs via X-Forwarded-For is a common foot-gun on shared hosts.
- Test config before reload: `nginx -t`, then `systemctl reload nginx`.
- A `location /` proxy is enough for most apps; deep path proxying needs care.

## Verify

```bash
nginx -t
curl -I https://skills.example.com/healthz
```
