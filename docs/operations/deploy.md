# Runbook — Deploy (production Ubuntu VM)

Authoritative deploy procedure. Dev mirrors it via `scripts/deploy.ps1`.
Substrate: **Hyper-V Ubuntu LTS VM + Docker Engine + Compose** (tech-stack §7).

Sequence — **backup → guard → explicit migrate → up**:

```sh
cd /opt/office-connect                       # repo checkout on the VM

# 1. Database up (backup + guard need it)
docker compose up -d db                       # wait for healthy

# 2. Fresh backup BEFORE migrating (also satisfies Guard A3)
docker compose run --rm worker python -m office_connect.ops backup

# 3. Deploy guard (release cuts a phase gate; dev = routine deploy)
docker compose run --rm -e OC_MIGRATE_ON_BOOT=false -v "$(pwd):/repo:ro" \
    app python -m office_connect.ops.deploy_guard --repo /repo --mode release

# 4. Explicit migrate step (flag OFF; production NEVER boot-migrates)
docker compose run --rm -e OC_MIGRATE_ON_BOOT=false app alembic upgrade head

# 5. Bring the stack up
docker compose up -d app worker beat          # single beat — never scale it
```

## Guards (`office_connect.ops.deploy_guard`)

| Guard | Mode | Check |
|---|---|---|
| A1 | dev+release | refuse boot-migration in prod (`APP_ENV=production` + `OC_MIGRATE_ON_BOOT`) |
| A2 | dev+release | exactly one Alembic head (no divergent history) |
| A3 | dev+release | if schema already deployed, a **fresh** dump (<1 h) must exist |
| B  | release | `APP_VERSION` has no `.devN` suffix |
| C  | release | `CHANGELOG.md [Unreleased]` has ≥1 real entry |

The git-tag existence check is host-side (`.git`/`git` are not in the image):
`git tag --list phase-<N>-complete` must be empty before a release.

## Production invariants

- **`APP_ENV=production`** and **`OC_MIGRATE_ON_BOOT` unset** — migrations are an
  explicit step, never on boot (multi-worker boot races + crash-loop DDL).
- **One `beat` instance.** Never `--scale beat`, never embed `--beat` on a scaled
  worker → duplicate nightly backups.
- **Version-skew rule.** Bump the `db` image tag and the `postgresql-client-N`
  package in `Dockerfile` together; the client major must be ≥ the server.
- Unattended boot: Hyper-V Automatic Start → systemd → `restart: unless-stopped`.
  Power-cycle-test before go-live.

## Rollback

The fresh dump from step 2 is the restore point. Follow
[backup-restore.md](backup-restore.md) → *DR restore*, then run the restore drill
(`verify_chain()`) against the restored data before flipping traffic back.

> **Push timing (Phase 0):** the first `git push` + `phase-0-complete` tag fires
> at the **Phase 0 QA gate** (end of Increment 4), after the off-box remote is
> provisioned — never mid-phase (development-workflow.md §4/§6).
