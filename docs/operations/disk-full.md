# Runbook — Disk Full

A full disk stops Postgres (it refuses writes) and can wedge the whole stack.
Docker volumes (`pgdata`), the local attachments store (`./storage`), backups
(`./backups`), and container logs are the usual culprits.

## 1. Confirm
```sh
df -h                      # host filesystem usage
docker system df           # images / containers / volumes / build cache
du -sh ./storage ./backups # attachments store + dumps
```
Symptoms: `/health` 503 with `postgres: error`; DB logs show `No space left on
device` / `could not extend file`.

## 2. Reclaim safely (least destructive first)
- **Prune old backups** beyond retention (nightly prune keeps `backup_retention`,
  default 7): remove verified-off-box older dumps from `./backups`.
- **Docker cruft**: `docker image prune` / `docker builder prune` (safe);
  `docker system prune` (careful — removes stopped containers/networks). **Never**
  `docker volume prune` (it can drop `pgdata`).
- **Container logs**: if the JSON logs grew large, ensure the daemon uses log
  rotation (`json-file` `max-size`/`max-file`), then restart.
- **Attachments store**: content-addressed and deduped; do **not** hand-delete
  blobs — orphan/retention cleanup is the attachments layer's job, and deletion
  is governed by the retention schedule (never bulk-delete records).

## 3. After space is recovered
```sh
docker compose restart db
curl -sS http://localhost:8001/health
```
Confirm Postgres accepts writes and `verify_chain()` is intact.

## 4. Prevent recurrence
- Add a disk-usage alert (Stage C observability).
- Ensure off-box backup copy + prune are running (`backup-restore.md`).
- Size the attachments volume for expected growth; the size cap
  (`attachment_max_bytes`) bounds per-file growth.
