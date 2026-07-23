# Runbook — Stack Down (service not responding)

When `https://<host>` / `http://localhost:8001` does not answer, work top-down.
The stack is the same containers on Windows dev and the production Ubuntu VM, so
the steps are identical.

## 1. Triage
```sh
docker compose ps                 # what is up / restarting / exited?
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8001/health || echo "app down"
```
- `/health` returns **200** healthy, **503** degraded (a dependency is down —
  the body's `checks` says which), or nothing (app process down).

## 2. Logs
```sh
docker compose logs --tail=200 app
docker compose logs --tail=100 db redis worker
```
Logs are structured JSON — filter by `request_id` to trace one request.

## 3. Common causes → actions
- **db unhealthy** → see `disk-full.md` (a full disk stops Postgres first);
  else `docker compose restart db` and re-check `pg_isready`.
- **redis down** → `docker compose restart redis`.
- **app import/migration error on boot** → check `alembic` head vs code; run the
  explicit migrate step (`deploy.md`), do **not** rely on boot-migrate in prod.
- **worker stuck** → `docker compose restart worker beat` (single beat only —
  never scale beat).
- **out of memory** (e.g. ClamAV profile enabled) → `docker stats`; the `clamav`
  profile needs ~1–3 GB.

## 4. Restart order
```sh
docker compose up -d db redis        # dependencies first (wait for healthy)
docker compose up -d app worker beat
```
Verify `/health` is 200 and `verify_chain()` is intact (see backup-restore.md).

## 5. If unrecoverable
- Restore from the latest good dump (`backup-restore.md`), or rebuild the host
  (`bare-metal-rebuild.md`). Escalate to the incident lead if data loss is
  suspected (`../compliance/breach-runbook.md`).
