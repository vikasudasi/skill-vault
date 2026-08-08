---
name: docker-compose-services
description: Run multi-service apps with Docker Compose — services, networks, volumes, healthchecks, and env config.
tags: [docker, compose, devops, containers, orchestration]
triggers: [docker compose, docker-compose, container orchestration, multi-service]
complexity: medium
time_estimate: 30-60 min
prerequisites: [docker, docker compose]
source: Skill Vault curated library
verify: true
---

# Docker Compose for Multi-Service Apps

Use when running several containers together (app + db + worker) on one host.

## Basic compose file

```yaml
services:
  web:
    build: .
    ports: ["8080:8080"]
    environment:
      - DATABASE_URL=postgres://u:p@db:5432/app
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:16
    environment:
      - POSTGRES_PASSWORD=p
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 5s
      timeout: 3s
      retries: 5
```

## Key practices

- Plug service-to-service refs over the compose network by **service name** (`db`),
  not `localhost`.
- Add `healthcheck` to dependencies and gate with `depends_on: condition`.
- Use volumes for durable data; bind mounts only for dev.

## Pitfalls

- **Compose merges override files**: a `docker-compose.override.yml` replaces the
  whole `ports:` list, it doesn't append. Use one standalone file or explicit
  overrides, or you'll reintroduce port conflicts.
- As root, `docker compose up -d` and `rm -rf` on mounted dirs can clobber host
  files — scope operations carefully.
- Prefer `docker compose config` to validate before `up`.

## Verify

```bash
docker compose config --quiet
docker compose ps
docker compose logs -f web
```
