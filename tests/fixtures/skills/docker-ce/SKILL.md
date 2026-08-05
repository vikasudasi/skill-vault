---
name: docker-ce
description: Operational runbooks for Docker CE on Ubuntu — containers, volumes, networks, and common failure recovery.
tags: [devops, docker, containers, ubuntu]
triggers: [docker, container, compose, image]
---

# Docker CE on Ubuntu

Use when the user is working with Docker containers on Ubuntu and needs an
operational runbook rather than a quick one-liner.

## Pull and run
```bash
docker pull ubuntu:24.04
docker run --rm -it ubuntu:24.04 bash
```

## Inspect
```bash
docker ps -a
docker images
docker logs --tail 100 <container>
```

## Common failure: port already in use
```
Error starting userland proxy: listen tcp4 0.0.0.0:8080: bind: address already in use
```
Find and stop the offending container:
```bash
docker ps -a --filter publish=8080
docker rm -f <container>
```

## Cleanup
```bash
docker system prune -a --volumes   # destroys unused images + all volumes
```
See `references/volumes.md` for volume persistence semantics.
