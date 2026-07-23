# Runbook — Bare-Metal Rebuild (disaster recovery)

Rebuild the production host from nothing (dead disk, lost VM, new server) and
restore service. Target: production is a **Hyper-V Ubuntu LTS VM with Docker
Engine + Compose** running the same images as dev (tech-stack §7). Prerequisite:
a recent **off-box** `pg_dump` (backup-restore.md) and this repository.

## 1. Provision the host
- Install Ubuntu LTS, Docker Engine, and the Compose plugin.
- Restore the app disk layout: the repo checkout, and the bind-mount dirs
  (`./backups`, `./storage`) — **restore `./storage` from its off-box copy** (the
  content-addressed attachment blobs are not in the DB dump).

## 2. Bring up datastores only
```sh
git clone <origin> office_connect && cd office_connect
cp <secure>/.env .env            # secrets: OC_APP_PASSWORD, POSTGRES_*, SESSION_SECRET, etc.
docker compose up -d db redis    # wait for db healthy
```

## 3. Recreate schema + restore data
```sh
docker compose run --rm app alembic upgrade head        # roles/grants + schema
# then restore the latest good dump into the running DB (as owner oc_dev):
docker compose exec worker python -m office_connect.ops restore-drill --file <dump>  # proof-restore into scratch
# for the REAL restore, pg_restore the dump into the primary DB per backup-restore.md
```
> Order matters: `alembic upgrade head` creates the `oc_app` role + grants; the
> data restore repopulates rows. Verify the audit chain after: `verify_chain()`
> must be intact (a broken chain means a bad/tampered dump).

## 4. Start the app + workers
```sh
docker compose up -d app worker beat
docker compose up -d proxy       # reverse proxy / TLS (cert-renewal.md)
```

## 5. Verify
- `/health` → 200; `/api/v1/config` → all flags OFF, no 500.
- `verify_chain()` intact; a spot-check of key rows.
- Re-seed reference data if needed (idempotent): `python -m office_connect.ops.bootstrap load-reference`.
- Confirm the nightly backup runs and lands off-box.

## 6. Post-recovery
- Record the incident + timeline.
- Rotate any secrets that may have been exposed during recovery.
- If personal data may have been at risk, follow `../compliance/breach-runbook.md`.
