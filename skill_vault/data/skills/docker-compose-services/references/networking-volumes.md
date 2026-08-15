# Networking & Volume Patterns

## Compose networking defaults

- All services join a default bridge network named `<project>_default`
- Services reach each other by **service name** (e.g., `db`, `redis`), NOT `localhost`
- Ports exposed to host: `"<host>:<container>"` — only expose what's needed

## Custom networks

```yaml
networks:
  frontend:
  backend:
    internal: true  # no external access
```

Attach services: `networks: [frontend, backend]` — isolate backend services like databases.

## Volume strategies

| Scenario | Volume type | Example |
|----------|-------------|---------|
| Database persistence | Named volume | `pgdata:/var/lib/postgresql/data` |
| Dev hot-reload | Bind mount | `./src:/app/src:ro` |
| Shared configs | Read-only bind mount | `./nginx.conf:/etc/nginx/conf.d/default.conf:ro` |
| Inter-service sharing | Named volume with alias | Same volume in multiple services |

## Healthcheck patterns

```
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]  # $$ escapes for shell
  interval: 5s
  timeout: 3s
  retries: 5
  start_period: 10s   # grace period after container start
```

Always gate dependencies with `depends_on: condition: service_healthy` — this ensures the database is accepting connections, not just that the container started.
