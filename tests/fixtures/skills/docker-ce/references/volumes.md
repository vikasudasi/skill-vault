# Volume persistence semantics

- **Named volumes** (`-v mydata:/data`) survive `docker rm` and `docker compose down`; they are removed only by `docker volume rm` or `docker system prune --volumes`.
- **Anonymous volumes** recurse mount data back into a rebuilt image on `docker compose up` unless you also pass `--renew-anon-volumes`.
- **Bind mounts** (`-v /host/path:/container/path`) always reflect the host filesystem; removing the container never deletes host files.
- Back up a named volume with a throwaway container:
  ```bash
  docker run --rm -v mydata:/data -v $(pwd):/backup ubuntu tar czf /backup/mydata.tgz -C /data .
  ```
