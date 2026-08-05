# Docker Volume Persistence Semantics

Persistence rules for Docker volumes referenced from the docker-ce runbook.

## Named volumes (persistent)

```bash
docker volume create mydata
docker run -v mydata:/data ...
```

Data survives container removal. Lives in `/var/lib/docker/volumes/`.

## Bind mounts (host paths)

```bash
docker run -v /host/path:/container/path ...
```

Directly maps a host directory. Changes on either side are immediately visible.
Best for config or dev code; riskier for app data (host filesystem semantics apply).

## Volumes vs container layer

Anything written to the container's writable layer is destroyed on `docker rm`.
Use a volume or bind mount for anything you must keep.

## Inspections

```bash
docker volume ls
docker inspect mydata        # Mountpoint
docker run --rm -v mydata:/data alpine ls -la /data
```

## Cleanup guards

`docker system prune -a --volumes` deletes **all** unused volumes — never run it
against data you intend to keep without a backup.
