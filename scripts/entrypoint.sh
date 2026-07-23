#!/bin/sh
# Office-Connect container entrypoint.
#
# Dev-only, env-gated boot migration: when OC_MIGRATE_ON_BOOT=true (the app
# service sets it in dev), run an advisory-locked `alembic upgrade head` so a
# fresh `docker compose up` comes up read-write with no manual step. Production
# leaves the flag OFF and runs the explicit migrate step instead — and this
# entrypoint HARD-REFUSES boot migration when APP_ENV=production regardless of
# the flag (belt and suspenders). Then it execs the service command (CMD).
set -e

if [ "${OC_MIGRATE_ON_BOOT:-false}" = "true" ]; then
    if [ "${APP_ENV}" = "production" ]; then
        echo "REFUSING: OC_MIGRATE_ON_BOOT is dev-only; production uses the explicit migrate step." >&2
        exit 1
    fi
    echo "[entrypoint] advisory-locked alembic upgrade head"
    python -m office_connect.core.migrate
fi

exec "$@"
