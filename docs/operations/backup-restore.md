# Runbook — Backup & Restore

Backups are `pg_dump -Fc` (custom format) taken **as the owner role `oc_dev`**
(the only role that can produce a full, restorable dump). They run in-container
(the image carries `postgresql-client-16`), so the procedure is identical on
Windows dev and the production Ubuntu VM.

## Schedule & placement (3-2-1)

- **Nightly** at 02:00 Asia/Manila via Celery beat (`ops.backup_database`) →
  `pg_dump -Fc` into `backups_dir` (`/app/backups`, bind-mounted to host
  `./backups`). Retention: newest `backup_retention` (default 7) dumps.
- **Off-box copy (the "1" of 3-2-1)** — a host-side step, NOT in-container:
  copy `./backups/*.dump` to a **second/external disk on the box**. Dev example:
  ```powershell
  robocopy .\backups E:\oc-backups *.dump /XO
  ```
  Prod (Ubuntu VM): `rsync -a --ignore-existing ./backups/ /mnt/backup-disk/oc/`
  plus a periodic offline copy. Dumps contain full DB data (real PII later) —
  keep off-box copies access-controlled and encrypt at rest before real data.

## Manual commands

```sh
docker compose exec worker python -m office_connect.ops backup            # dump + prune
docker compose exec worker python -m office_connect.ops restore-drill --file latest
docker compose exec worker python -m office_connect.ops backup-and-drill   # the proof
```

## The proven-restore drill (QA gate + quarterly)

`backup-and-drill` is the free integrity check:

1. If the audit chain is empty **and** the env is not production, seed a real
   ≥3-link chain (insert + update + soft_delete) so the check isn't vacuously
   green. (Never runs against production data.)
2. `pg_dump -Fc` the DB.
3. `createdb` a throwaway scratch DB (name-guarded so a drop can never hit the
   real DB), `pg_restore --single-transaction --exit-on-error` into it.
4. Load `core_audit_logs` ordered by id and run `verify_chain()` — must be
   non-empty and unbroken.
5. `dropdb --force` the scratch DB (always, even on failure).

Any failure raises loudly (non-zero exit). Run quarterly per master-plan §3.2.

## DR restore (real recovery)

Restore into a **fresh, empty** database — never over a populated one, never
with `pg_restore --clean` against live data:

```sh
createdb --owner=oc_dev office_connect_restored
pg_restore --dbname=office_connect_restored --single-transaction --exit-on-error <dump>
# then verify integrity before cutover:
docker compose exec worker python -m office_connect.ops restore-drill --file <dump>
```

A single-DB `-Fc` dump does **not** contain roles/passwords (cluster globals).
For a bare-metal cluster rebuild also keep a `pg_dumpall --globals-only` file
(treat it as a secret) — planned as a Stage A ops follow-up.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pg_dump: server version mismatch` | client major < server | bump `postgresql-client-N` to match the `db` image |
| `permission denied to create database` | ran as `oc_app` | backup/drill must use `oc_dev` (`MIGRATION_DATABASE_URL`) |
| drill "restored audit chain is EMPTY" | nothing to verify | expected only if seeding was skipped (production/non-empty) |
| `database is being accessed by other users` on drop | lingering connection | drill uses `dropdb --force`; ensure the verify engine disposed |
