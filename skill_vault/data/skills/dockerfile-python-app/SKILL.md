---
name: dockerfile-python-app
description: Write an efficient, secure Dockerfile for a Python app — layer caching, slim images, non-root user, and healthchecks.
tags: [docker, dockerfile, python, container, devops]
triggers: [dockerfile, containerize, build image, best practices]
complexity: medium
time_estimate: 30-60 min
prerequisites: [docker, a python project]
source: Skill Vault curated library
verify: true
---

# Dockerfile for a Python App

Use when containerizing a Python service with a small, cache-friendly, secure image.

## Efficient + secure Dockerfile

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first so layer cache survives code changes
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Add code last
COPY . .

# Run as non-root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

## Build-time tips (T3-style — each RUN is a layer)

- `COPY` only what a step needs, after install → code changes don't rebuild deps.
- Combine `RUN` commands with `&&` and clean caches in the same layer.
- Use `--no-cache-dir` to keep images slim.

## Security

- Default to a **non-root user** — never run the app as root in the image.
- Pin base image tags; prefer `-slim` over full to shrink attack surface.
- Don't `COPY` secrets; inject at runtime via env/secrets.

## Multi-stage (build vs runtime)

Keep the builder and runtime separate when you compile assets or build wheels:

```dockerfile
FROM python:3.12 AS builder
# ...build...
FROM python:3.12-slim AS runtime
COPY --from=builder /app /app
```

## Pitfalls

- `.dockerignore` matters — it also stops git metadata from breaking builds.
- Streaming logs need `PYTHONUNBUFFERED=1`, or uvicorn output buffers.
